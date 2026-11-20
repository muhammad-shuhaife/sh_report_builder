from io import BytesIO
from PIL import Image, ImageEnhance, UnidentifiedImageError
import re
from xml.sax.saxutils import escape, quoteattr

from lxml import etree

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.image import image_data_uri

# {{field}} or {{many2one_field.sub_field}}
TOKEN_RE = re.compile(r'\{\{\s*([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*\}\}')
COLOR_RE = re.compile(r'^(#[0-9a-fA-F]{3,8}|[a-zA-Z]{3,20})$')

FONT_FAMILIES = {
    'sans': "Helvetica, Arial, sans-serif",
    'serif': "Georgia, 'Times New Roman', serif",
    'mono': "'Courier New', Courier, monospace",
    'dejavu_sans': "'DejaVu Sans', sans-serif",
    'dejavu_serif': "'DejaVu Serif', serif",
    'dejavu_mono': "'DejaVu Sans Mono', monospace",
    'liberation_sans': "'Liberation Sans', Arial, sans-serif",
    'liberation_serif': "'Liberation Serif', 'Times New Roman', serif",
    'carlito': "Carlito, Calibri, sans-serif",
    'caladea': "Caladea, Cambria, serif",
    'gentium': "Gentium, Georgia, serif",
}


class ReportBuilder(models.Model):
    _name = 'report.builder'
    _description = 'Report Design'
    _order = 'name, id'

    name = fields.Char('Report Name', required=True, translate=False,
                       help="Shown in the Print menu of the selected model.")
    active = fields.Boolean(default=True)
    state = fields.Selection(
        [('draft', 'Draft'), ('published', 'Published')],
        default='draft', readonly=True, copy=False)
    model_id = fields.Many2one(
        'ir.model', string='Applies To', required=True, ondelete='cascade',
        domain=[('transient', '=', False)],
        help="The kind of record this report prints (Sales Order, Invoice, Contact...).")
    model_name = fields.Char(related='model_id.model', store=True, string='Model Name')
    layout = fields.Selection(
        [('company', 'Odoo company header & footer'),
         ('custom', 'Custom header & footer (image or designed)'),
         ('minimal', 'Blank page (no header / footer)')],
        default='company', required=True)
    print_name = fields.Char(
        'PDF File Name',
        help="File name of the downloaded PDF. Use {{field}} placeholders, "
             "e.g. Quotation {{name}}. Also supports {{report_name}} and {{date}}.")

    # ---- look & feel -------------------------------------------------
    primary_color = fields.Char('Accent Colour', default='#714B67')
    font_family = fields.Selection(
        [('default', 'Odoo default'), ('sans', 'Sans-serif'),
         ('serif', 'Serif'), ('mono', 'Monospace'),
         ('dejavu_sans', 'DejaVu Sans'), ('dejavu_serif', 'DejaVu Serif'),
         ('dejavu_mono', 'DejaVu Sans Mono'), ('liberation_sans', 'Liberation Sans'),
         ('liberation_serif', 'Liberation Serif'), ('carlito', 'Carlito'),
         ('caladea', 'Caladea'), ('gentium', 'Gentium')],
        default='default', required=True)
    font_size = fields.Integer('Base Font Size (pt)', default=10)
    use_custom_colors = fields.Boolean('Choose multiple colours')
    text_color = fields.Char('Body text', default='#222222')
    heading_color = fields.Char('Headings', default='#714B67')
    table_header_color = fields.Char('Table header background', default='#714B67')
    table_header_text_color = fields.Char('Table header text', default='#ffffff')
    stripe_color = fields.Char('Alternate rows', default='#f5f5f5')
    total_color = fields.Char('Totals background', default='#ffffff')
    border_color = fields.Char('Table borders', default='#dddddd')
    use_background_image = fields.Boolean('Use a background image')
    background_image = fields.Binary('Background image', attachment=True)
    background_opacity = fields.Integer(
        'Background opacity (%)', default=10,
        help='0 = invisible, 100 = original image. Text and tables stay fully opaque.')
    background_saturation = fields.Integer(
        'Background saturation (%)', default=100,
        help='0 = grayscale, 100 = original colours, 200 = stronger colours. Opacity is controlled separately.')
    background_fit = fields.Selection(
        [('contain', 'Fit whole image'), ('cover', 'Fill (may crop)'),
         ('repeat', 'Repeat pattern')], default='contain', required=True)

    custom_css = fields.Text(
        'Custom CSS',
        help="Advanced. Applied to the whole report. Scope your rules with "
             ".rb-report. Avoid the '>' selector. wkhtmltopdf has no flexbox/grid support.")

    # ---- paper -------------------------------------------------------
    paper_format_source = fields.Selection(
        [('custom', 'Configure for this report'), ('existing', 'Use an existing paper format')],
        default='custom', required=True, string='Paper format setup')
    existing_paperformat_id = fields.Many2one(
        'report.paperformat', string='Existing paper format', ondelete='restrict',
        help='Settings are copied into this report’s own paper format when previewing or publishing. Shared formats are never modified.')

    paper_format = fields.Selection(
        [('A4', 'A4'), ('A5', 'A5'), ('A3', 'A3'),
         ('Letter', 'US Letter'), ('Legal', 'US Legal')],
        default='A4', required=True)
    orientation = fields.Selection(
        [('Portrait', 'Portrait'), ('Landscape', 'Landscape')],
        default='Portrait', required=True)
    margin_top = fields.Integer('Top (mm)', default=40)
    margin_bottom = fields.Integer('Bottom (mm)', default=20)
    margin_left = fields.Integer('Left (mm)', default=7)
    margin_right = fields.Integer('Right (mm)', default=7)
    header_spacing = fields.Integer(
        'Header Spacing (mm)', default=35,
        help="Gap kept between the header and the report body. If the header overlaps "
             "the body, increase Top margin. A larger gap leaves less room for the header.")

    # ---- content -----------------------------------------------------
    block_ids = fields.One2many('report.builder.block', 'builder_id',
                                string='Blocks', copy=True,
                                domain=[('zone', '=', 'body')])

    # ---- custom header / footer ---------------------------------------
    header_mode = fields.Selection(
        [('none', 'None'), ('image', 'Upload an image'), ('design', 'Design it')],
        string='Header', default='image', required=True)
    header_image = fields.Binary('Header Image', attachment=True)
    header_image_height = fields.Integer(
        'Maximum header image height (mm)', default=20,
        help='Image keeps its proportions and fits within this height and the printable width.')
    header_block_ids = fields.One2many('report.builder.block', 'builder_id',
                                       string='Header Blocks', copy=True,
                                       domain=[('zone', '=', 'header')])
    footer_mode = fields.Selection(
        [('none', 'None'), ('image', 'Upload an image'), ('design', 'Design it')],
        string='Footer', default='image', required=True)
    footer_image = fields.Binary('Footer Image', attachment=True)
    footer_image_height = fields.Integer(
        'Maximum footer image height (mm)', default=12,
        help='Image keeps its proportions and fits within this height and the printable width.')
    footer_block_ids = fields.One2many('report.builder.block', 'builder_id',
                                       string='Footer Blocks', copy=True,
                                       domain=[('zone', '=', 'footer')])
    block_count = fields.Integer(compute='_compute_counts')
    has_blocks = fields.Boolean(compute='_compute_counts')

    # ---- preview / output --------------------------------------------
    preview_record_id = fields.Many2oneReference(
        'Preview Record', model_field='model_name', copy=False,
        help="Record used by the Preview buttons. Leave empty to use the first one found.")
    generated_arch = fields.Text('Generated QWeb', compute='_compute_generated_arch')
    view_id = fields.Many2one('ir.ui.view', readonly=True, copy=False, ondelete='set null')
    action_id = fields.Many2one('ir.actions.report', readonly=True, copy=False,
                                ondelete='set null')
    paperformat_id = fields.Many2one('report.paperformat', readonly=True, copy=False,
                                     ondelete='set null')

    # ------------------------------------------------------------------
    # computes / onchanges
    # ------------------------------------------------------------------
    def write(self, values):
        if 'model_id' in values and any(
                rec.state == 'published' and rec.model_id.id != values['model_id']
                for rec in self):
            raise UserError(_('Unpublish the report before changing Applies To.'))
        return super().write(values)

    @api.depends('block_ids')
    def _compute_counts(self):
        for rec in self:
            rec.block_count = len(rec.block_ids)
            rec.has_blocks = bool(rec.block_ids)

    @api.depends('block_ids', 'header_block_ids', 'footer_block_ids', 'layout',
                 'primary_color', 'font_family', 'font_size', 'custom_css', 'model_id',
                 'header_mode', 'footer_mode', 'header_image', 'footer_image',
                 'use_custom_colors', 'text_color', 'heading_color', 'table_header_color',
                 'table_header_text_color', 'stripe_color', 'total_color', 'border_color',
                 'use_background_image', 'background_image', 'background_fit', 'background_opacity', 'background_saturation',
                 'header_image_height', 'footer_image_height', 'page_design', 'line_design',
                 'body_design', 'body_design_color', 'body_design_opacity', 'body_design_watermark',
                 'header_repeat', 'footer_repeat', 'page_number_display', 'background_mode',
                 'background_scale', 'background_position')
    def _compute_generated_arch(self):
        for rec in self:
            if not rec.id:
                rec.generated_arch = ''
                continue
            try:
                arch = rec._build_full_arch()
                rec.generated_arch = etree.tostring(
                    etree.fromstring(arch.encode()), pretty_print=True,
                    encoding='unicode')
            except UserError as exc:
                rec.generated_arch = '<!-- %s -->' % str(exc.args[0]).replace('--', '- -')

    @api.onchange('layout')
    def _onchange_layout(self):
        if self.layout == 'company':
            self.margin_top, self.margin_bottom, self.header_spacing = 40, 20, 35
        elif self.layout == 'custom':
            self.margin_top, self.margin_bottom, self.header_spacing = 40, 25, 5
        else:
            self.margin_top, self.margin_bottom, self.header_spacing = 12, 12, 0

    def copy_data(self, default=None):
        vals_list = super().copy_data(default)
        for vals in vals_list:
            if not (default and 'name' in default):
                vals['name'] = _('%s (copy)', vals.get('name', ''))
        return vals_list

    # ------------------------------------------------------------------
    # helpers used by blocks
    # ------------------------------------------------------------------
    def _report_key(self):
        self.ensure_one()
        return 'sh_report_builder.custom_%s' % self.id

    @staticmethod
    def _safe_color(value):
        value = (value or '').strip()
        return value if COLOR_RE.match(value) else ''

    def _resolve_field(self, model_name, path):
        """Walk ``path`` (a.b.c) starting from ``model_name``; return the last ORM field."""
        if model_name not in self.env:
            raise UserError(_("Unknown model '%s'.", model_name))
        model = self.env[model_name]
        parts = path.split('.')
        field = None
        for idx, part in enumerate(parts):
            field = model._fields.get(part)
            if field is None:
                raise UserError(_("Unknown field '%(field)s' on model %(model)s.",
                                  field=part, model=model._name))
            if idx < len(parts) - 1:
                if not field.comodel_name:
                    raise UserError(_("'%(field)s' is not a relation, so '%(path)s' is invalid.",
                                      field=part, path=path))
                model = self.env[field.comodel_name]
        return field

    def _value_node(self, root, path, model_name):
        """QWeb snippet printing ``root.path`` with the right formatting."""
        if path.startswith('company.'):
            root, path, model_name = 'company', path[len('company.'):], 'res.company'
        field = self._resolve_field(model_name, path)
        expr = '%s.%s' % (root, path)
        if field.type in ('one2many', 'many2many'):
            return '<span t-out=%s/>' % quoteattr(
                "', '.join(%s.mapped('display_name'))" % expr)
        if field.type == 'boolean':
            return '<span t-out=%s/>' % quoteattr("'Yes' if %s else 'No'" % expr)
        if field.type == 'binary':
            return '<img t-if=%s t-att-src=%s style="max-height:60px;max-width:100%%;"/>' % (
                quoteattr(expr), quoteattr('image_data_uri(%s)' % expr))
        return '<span t-field=%s/>' % quoteattr(expr)

    def _text_to_xml(self, text):
        """Escape ``text`` and turn {{field}} placeholders / newlines into QWeb."""
        self.ensure_one()
        text = text or ''
        out, pos = [], 0
        for match in TOKEN_RE.finditer(text):
            out.append(escape(text[pos:match.start()]))
            token = match.group(1)
            if token in ('page', 'topage'):
                # replaced by wkhtmltopdf in headers/footers
                out.append('<span class="%s"></span>' % token)
            else:
                out.append(self._value_node('o', token, self.model_name))
            pos = match.end()
        out.append(escape(text[pos:]))
        return ''.join(out).replace('\r\n', '\n').replace('\n', '<br/>')

    def _print_name_expr(self):
        """Python expression for ir.actions.report.print_report_name."""
        self.ensure_one()
        pattern = self.print_name or self.name or 'Report'
        parts, pos = [], 0
        for match in TOKEN_RE.finditer(pattern):
            if match.start() > pos:
                parts.append(repr(pattern[pos:match.start()]))
            path = match.group(1)
            field = self._resolve_field(self.model_name, path)
            suffix = '.display_name' if field.type == 'many2one' else ''
            parts.append("str(object.%s%s or '')" % (path, suffix))
            pos = match.end()
        if pos < len(pattern):
            parts.append(repr(pattern[pos:]))
        return ' + '.join(parts) or "'Report'"

    # ------------------------------------------------------------------
    # arch generation
    # ------------------------------------------------------------------
    def _background_data_uri(self):
        opacity = self.background_opacity
        if not 0 <= opacity <= 100:
            raise UserError(_("Background opacity must be between 0 and 100 percent."))
        saturation = self.background_saturation
        if not 0 <= saturation <= 200:
            raise UserError(_('Background saturation must be between 0 and 200 percent.'))
        if opacity == 100 and saturation == 100:
            return image_data_uri(self.background_image)
        # Apply alpha to the image itself: page content remains fully opaque,
        # including in the PDF renderer and across page breaks.
        try:
            with Image.open(BytesIO(bytes(self.background_image))) as source:
                image = source.convert('RGBA')
                alpha = image.getchannel('A').point(lambda value: round(value * opacity / 100))
                if saturation != 100:
                    image = ImageEnhance.Color(image.convert('RGB')).enhance(saturation / 100).convert('RGBA')
                image.putalpha(alpha)
                output = BytesIO()
                image.save(output, format='PNG')
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise UserError(_("Upload a PNG or JPEG background to adjust its opacity and saturation.")) from exc
        return image_data_uri(output.getvalue())

    def _build_css(self):
        self.ensure_one()
        color = self._safe_color(self.primary_color) or '#714B67'
        css = (
            ".rb-report table.rb-table{width:100%;border-collapse:collapse;}"
            ".rb-report table.rb-table th{background-color:ACCENT;color:#ffffff;"
            "padding:6px 8px;}"
            ".rb-report table.rb-table td{padding:5px 8px;border-bottom:1px solid #dddddd;}"
            ".rb-report table.rb-table.rb-striped tbody tr:nth-child(even) td"
            "{background-color:#f5f5f5;}"
            ".rb-report table.rb-table tfoot td{border-top:2px solid ACCENT;"
            "border-bottom:0;padding:6px 8px;}"
            ".rb-report h1,.rb-report h2,.rb-report h3,.rb-report h4{color:ACCENT;}"
        ).replace('ACCENT', color)
        if self.use_custom_colors:
            palette = {
                'text': self._safe_color(self.text_color) or '#222222',
                'heading': self._safe_color(self.heading_color) or color,
                'header': self._safe_color(self.table_header_color) or color,
                'header_text': self._safe_color(self.table_header_text_color) or '#ffffff',
                'stripe': self._safe_color(self.stripe_color) or '#f5f5f5',
                'total': self._safe_color(self.total_color) or '#ffffff',
                'border': self._safe_color(self.border_color) or '#dddddd',
            }
            css += (
                '.rb-report{color:%(text)s;}'
                '.rb-report h1,.rb-report h2,.rb-report h3,.rb-report h4{color:%(heading)s;}'
                '.rb-report table.rb-table th{background:%(header)s;color:%(header_text)s;}'
                '.rb-report table.rb-table td{border-bottom-color:%(border)s;}'
                '.rb-report table.rb-table.rb-striped tbody tr:nth-child(even) td{background:%(stripe)s;}'
                '.rb-report table.rb-table tfoot td{background:%(total)s;border-top-color:%(border)s;}'
            ) % palette
        if self.use_background_image and self.background_image and self.background_mode != 'watermark':
            fit = self.background_fit if self.background_fit in ('cover', 'contain') else 'auto'
            repeat = 'repeat' if self.background_fit == 'repeat' else 'no-repeat'
            css += ('.rb-report{background-image:url("%s");background-size:%s;'
                    'background-repeat:%s;background-position:center center;}') % (
                        self._background_data_uri(), fit, repeat)
        if self.use_background_image and self.background_image and self.background_mode == 'watermark':
            css += 'body,.o_body_pdf,main,.article,.page{background-color:transparent!important;}.rb-report{position:relative;}.rb-report-content{position:relative;z-index:1;}.rb-report table.rb-table td{background-color:transparent!important;}'
        user_css = (self.custom_css or '').replace('&', '&amp;').replace('<', '&lt;')
        return css + user_css

    def _zone_xml(self, zone):
        """Header or footer ``<div>`` for the custom layout ('' when empty)."""
        self.ensure_one()
        mode = self['%s_mode' % zone]
        if mode == 'none':
            return ''
        if mode == 'image':
            data = self['%s_image' % zone]
            if not data:
                return ''
            # Odoo 20 binary fields return BinaryValue objects, not base64 text.
            content = '<img src=%s style="width:100%%;height:auto;display:block;margin:0;"/>' % quoteattr(
                image_data_uri(data))
        else:
            blocks = self['%s_block_ids' % zone].filtered('enabled').sorted(
                key=lambda b: (b.sequence, b._origin.id or 0))
            if not blocks:
                return ''
            content = ''.join(block._render_block() for block in blocks)
        return '<div class="%s" style=%s>%s</div>' % (
            zone, quoteattr('margin:0;padding:0;font-size:%dpt;font-family:%s' % (
                self.font_size or 10, FONT_FAMILIES.get(self.font_family, 'sans-serif'))),
            content)

    def _build_full_arch(self):
        self.ensure_one()
        blocks = self.block_ids.filtered('enabled').sorted(key=lambda b: (b.sequence, b._origin.id or 0))
        if not blocks:
            raise UserError(_("Add at least one enabled block to the design first."))
        body = ''.join(block._render_block() for block in blocks)
        page_style = ['font-size:%dpt' % (self.font_size or 10)]
        if self.font_family in FONT_FAMILIES:
            page_style.append('font-family:%s' % FONT_FAMILIES[self.font_family])
        page = '<div class="page rb-report" style=%s><style>%s</style>%s</div>' % (
            quoteattr(';'.join(page_style)), self._build_css(), self._watermark_xml() + '<div class="rb-report-content">' + body + '</div>')

        # 'company' is available to every block (and to {{company.xxx}} placeholders)
        company_expr = ('o.company_id or res_company'
                        if 'company_id' in self.env[self.model_name]._fields
                        else 'res_company')
        set_company = '<t t-set="company" t-value=%s/>' % quoteattr(company_expr)

        if self.layout == 'custom':
            inner = (
                '%(header)s'
                '<div class="article o_report_layout_standard" '
                't-att-data-oe-model="o and o._name" t-att-data-oe-id="o and o.id" '
                't-att-data-oe-lang="o and o.env.context.get(\'lang\')">%(page)s</div>'
                '%(footer)s'
            ) % {'header': self._zone_xml('header'), 'page': page,
                 'footer': self._zone_xml('footer')}
        else:
            layout = 'web.external_layout' if self.layout == 'company' else 'web.basic_layout'
            inner = '<t t-call="%s">%s</t>' % (layout, page)
        arch = (
            '<t t-name=%s><t t-call="web.html_container">'
            '<t t-foreach="docs" t-as="o">%s%s</t></t></t>'
        ) % (quoteattr(self._report_key()), set_company, inner)
        try:
            etree.fromstring(arch.encode())
        except etree.XMLSyntaxError as exc:
            raise UserError(_("The generated report is not valid XML: %s", exc))
        return arch

    # ------------------------------------------------------------------
    # publishing
    # ------------------------------------------------------------------
    def _base_paper_values(self):
        if self.paper_format_source == 'existing':
            source = self.existing_paperformat_id
            if not source:
                raise UserError(_("Select an existing paper format in the Paper Format tab."))
            names = ('format', 'orientation', 'page_width', 'page_height',
                     'margin_top', 'margin_bottom', 'margin_left', 'margin_right',
                     'header_spacing', 'header_line', 'dpi', 'disable_shrinking')
            return {name: source[name] for name in names if name in source._fields}
        return {
            'format': self.paper_format, 'orientation': self.orientation,
            'page_width': 0, 'page_height': 0,
            'margin_top': self.margin_top, 'margin_bottom': self.margin_bottom,
            'margin_left': self.margin_left, 'margin_right': self.margin_right,
            'header_spacing': self.header_spacing, 'header_line': False,
            'dpi': 90, 'disable_shrinking': False,
        }

    def _banner_paper_values(self):
        """Honor the selected paper margins without automatic banner overrides."""
        base = self._base_paper_values()
        return {key: base[key] for key in ('margin_top', 'margin_bottom', 'header_spacing')}

    def _sync_records(self, bind):
        """Create/update the QWeb view, paper format and report action."""
        self.ensure_one()
        key = self._report_key()
        arch = self._build_full_arch()

        view_vals = {
            'name': 'Report Builder: %s' % self.name,
            'type': 'qweb',
            'key': key,
            'arch': arch,
        }
        if self.view_id:
            self.view_id.write(view_vals)
        else:
            self.view_id = self.env['ir.ui.view'].create(view_vals)
            self.env['ir.model.data'].create({
                'module': 'sh_report_builder',
                'name': 'custom_%s' % self.id,
                'model': 'ir.ui.view',
                'res_id': self.view_id.id,
                'noupdate': True,
            })

        pf_vals = self._base_paper_values()
        pf_vals['name'] = 'Report Builder: %s' % self.name
        pf_vals.update(self._banner_paper_values())
        if self.paperformat_id:
            self.paperformat_id.write(pf_vals)
        else:
            self.paperformat_id = self.env['report.paperformat'].create(pf_vals)

        action_vals = {
            'name': self.name,
            'model': self.model_name,
            'report_type': 'qweb-pdf',
            'report_name': key,
            'print_report_name': self._print_name_expr(),
            'paperformat_id': self.paperformat_id.id,
            'binding_model_id': self.model_id.id if bind else False,
            'binding_type': 'report',
        }
        # Tolerate fields renamed/removed between Odoo versions.
        known = self.env['ir.actions.report']._fields
        action_vals = {k: v for k, v in action_vals.items() if k in known}
        if self.action_id:
            self.action_id.write(action_vals)
        else:
            self.action_id = self.env['ir.actions.report'].create(action_vals)

    def action_publish(self):
        for rec in self:
            rec._sync_records(bind=True)
            rec.state = 'published'
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Report published'),
                'message': _('Find it under the Print menu of the %s form.',
                             self[:1].model_id.name),
                'type': 'success',
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    def action_unpublish(self):
        for rec in self:
            if rec.action_id:
                rec.action_id.write({'binding_model_id': False})
            rec.state = 'draft'

    def _preview(self, kind):
        self.ensure_one()
        self._sync_records(bind=(self.state == 'published'))
        res_id = self.preview_record_id
        if not res_id:
            sample = self.env[self.model_name].search([], limit=1)
            if not sample:
                raise UserError(_("Create at least one %s record to preview the report.",
                                  self.model_id.name))
            res_id = sample.id
        return {
            'type': 'ir.actions.act_url',
            'url': '/report/%s/%s/%s' % (kind, self.action_id.report_name, res_id),
            'target': 'new',
        }

    def action_preview_html(self):
        return self._preview('html')

    def action_preview_pdf(self):
        return self._preview('pdf')

    # ------------------------------------------------------------------
    # starter layout
    # ------------------------------------------------------------------
    def action_load_starter(self):
        Fields = self.env['ir.model.fields']

        def pick(model_name, names, limit=None):
            found = Fields.search([('model', '=', model_name), ('name', 'in', names)])
            ordered = [f for n in names for f in found if f.name == n]
            return ordered[:limit] if limit else ordered

        def items(fields_):
            return [(0, 0, {'sequence': i * 10, 'field_id': f.id})
                    for i, f in enumerate(fields_, 1)]

        for rec in self:
            if rec.block_ids:
                raise UserError(_("This design already has blocks."))
            model = rec.model_name
            blocks = [(0, 0, {'sequence': 10, 'block_type': 'heading',
                              'heading_level': '1', 'text': rec.name,
                              'margin_bottom': 14})]

            header = pick(model, ['name', 'partner_id', 'date_order', 'invoice_date',
                                  'date', 'user_id', 'state'], limit=6)
            if not header:
                header = pick(model, ['display_name'])
            blocks.append((0, 0, {'sequence': 20, 'block_type': 'fields',
                                  'columns': '2', 'item_ids': items(header),
                                  'margin_bottom': 14}))

            o2m = Fields.search([('model', '=', model), ('ttype', '=', 'one2many')])
            preferred = ['order_line', 'invoice_line_ids', 'move_ids_without_package',
                         'move_line_ids', 'line_ids']
            table_field = next((f for n in preferred for f in o2m if f.name == n), o2m[:1])
            if model == 'res.partner':
                table_field = False
            if table_field:
                cols = pick(table_field.relation,
                            ['name', 'product_id', 'product_uom_qty', 'quantity',
                             'price_unit', 'price_subtotal'], limit=5)
                if not cols:
                    cols = pick(table_field.relation, ['display_name'])
                blocks.append((0, 0, {'sequence': 30, 'block_type': 'table',
                                      'table_field_id': table_field.id,
                                      'show_index': False, 'striped': True,
                                      'item_ids': items(cols), 'margin_bottom': 14}))

            totals = pick(model, ['amount_untaxed', 'amount_tax', 'amount_total'])
            if totals:
                blocks.append((0, 0, {'sequence': 40, 'block_type': 'totals',
                                      'item_ids': items(totals)}))
            rec.block_ids = blocks

    def action_load_header_footer(self):
        return self._load_zone_starters(('header', 'footer'))

    def action_load_header(self):
        return self._load_zone_starters(('header',))

    def action_load_footer(self):
        return self._load_zone_starters(('footer',))

    def _load_zone_starters(self, zones):
        # Validate the entire selection before changing any design.
        for rec in self:
            for zone in zones:
                if rec['%s_block_ids' % zone]:
                    raise UserError(_("This section already has design blocks. Edit those blocks instead."))
        for rec in self:
            starters = {
                'layout': 'custom', 'header_mode': 'design', 'footer_mode': 'design',
                'header_block_ids': [
                    (0, 0, {'zone': 'header', 'sequence': 10, 'block_type': 'twocol',
                            'show_logo': True, 'height': 60, 'margin_bottom': 6,
                            'text_right': "{{company.name}}\n{{company.street}}\n"
                                          "{{company.city}} {{company.zip}}\n{{company.phone}}"}),
                    (0, 0, {'zone': 'header', 'sequence': 20, 'block_type': 'divider',
                            'margin_bottom': 0}),
                ],
                'footer_block_ids': [
                    (0, 0, {'zone': 'footer', 'sequence': 10, 'block_type': 'divider',
                            'margin_bottom': 4}),
                    (0, 0, {'zone': 'footer', 'sequence': 20, 'block_type': 'text',
                            'align': 'center', 'font_size': 8, 'margin_bottom': 2,
                            'text': "{{company.name}}  |  {{company.email}}  |  {{company.website}}"}),
                    (0, 0, {'zone': 'footer', 'sequence': 30, 'block_type': 'text',
                            'align': 'center', 'font_size': 8, 'margin_bottom': 0,
                            'text': "Page {{page}} / {{topage}}"}),
                ],
            }
            vals = {'layout': 'custom'}
            for zone in zones:
                vals['%s_mode' % zone] = 'design'
                vals['%s_block_ids' % zone] = starters['%s_block_ids' % zone]
            changed_layout = rec.layout != 'custom'
            rec.write(vals)
            if changed_layout:
                rec._onchange_layout()

    # ------------------------------------------------------------------
    # cleanup
    # ------------------------------------------------------------------
    def unlink(self):
        actions, formats, views = self.action_id, self.paperformat_id, self.view_id
        actions.write({'binding_model_id': False})
        res = super().unlink()
        actions.unlink()
        formats.unlink()
        views.unlink()
        return res
