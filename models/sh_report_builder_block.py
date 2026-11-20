from xml.sax.saxutils import escape, quoteattr

from lxml import etree

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.image import image_data_uri

BLOCK_TYPES = [
    ('heading', 'Heading'),
    ('text', 'Text'),
    ('fields', 'Field list'),
    ('table', 'Table (lines)'),
    ('totals', 'Totals'),
    ('image', 'Image'),
    ('twocol', 'Two columns (logo / text)'),
    ('signature', 'Signature lines'),
    ('divider', 'Divider line'),
    ('spacer', 'Spacer'),
    ('pagebreak', 'Page break'),
    ('code', 'Custom QWeb (advanced)'),
]


class ReportBuilderBlock(models.Model):
    _name = 'report.builder.block'
    _description = 'Report Design Block'
    _order = 'sequence, id'

    builder_id = fields.Many2one('report.builder', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    zone = fields.Selection([('body', 'Body'), ('header', 'Header'), ('footer', 'Footer')],
                            default='body', required=True, index=True)
    enabled = fields.Boolean('Show', default=True)
    block_type = fields.Selection(BLOCK_TYPES, string='Type', required=True, default='text')
    summary = fields.Char(compute='_compute_summary')
    model_name = fields.Char(related='builder_id.model_name')
    source_model = fields.Char(
        compute='_compute_source_model',
        help="Model whose fields can be used in this block's rows.")

    # content
    text = fields.Text(
        help="Use {{field_name}} or {{many2one.field}} to insert values, e.g. "
             "'Dear {{partner_id.name}},'. For signature blocks: one label per line.")
    heading_level = fields.Selection(
        [('1', 'Title'), ('2', 'Section'), ('3', 'Sub-section'), ('4', 'Small')],
        default='2')
    columns = fields.Selection([('1', '1 column'), ('2', '2 columns'), ('3', '3 columns')],
                               default='2')
    table_field_id = fields.Many2one(
        'ir.model.fields', string='Rows Come From', ondelete='cascade',
        help="The list field whose records become table rows (e.g. Order Lines).")
    item_ids = fields.One2many('report.builder.item', 'block_id', string='Fields', copy=True)
    show_index = fields.Boolean('Row Numbers')
    striped = fields.Boolean('Striped Rows', default=True)

    # image
    image_source = fields.Selection(
        [('static', 'Upload an image'), ('field', 'Image field of the record'),
         ('company', 'Company logo')],
        default='static')
    show_logo = fields.Boolean('Company Logo on the Left',
                               help="Show the company logo on the left instead of text.")
    text_right = fields.Text('Right Column Text',
                             help="Aligned to the right. Supports {{company.name}}, "
                                  "{{company.phone}}, {{page}}, {{topage}}...")
    image_field_id = fields.Many2one('ir.model.fields', string='Image Field',
                                     ondelete='cascade')
    image = fields.Binary(attachment=True)
    image_width = fields.Integer('Width (px)', help="0 = automatic size (max 90px tall).")

    # spacing / style
    height = fields.Integer('Height (px)', default=30)
    align = fields.Selection([('left', 'Left'), ('center', 'Centre'), ('right', 'Right')],
                             default='left')
    font_size = fields.Integer('Font Size (pt)', help="0 = inherit from the report.")
    bold = fields.Boolean()
    color = fields.Char('Text Colour')
    background = fields.Char('Background')
    margin_top = fields.Integer('Space Above (px)', default=0)
    margin_bottom = fields.Integer('Space Below (px)', default=10)
    border_bottom = fields.Boolean('Underline')

    # advanced
    condition = fields.Char(
        'Show Only If',
        help="Optional QWeb condition, e.g. o.state == 'sale'. 'o' is the printed record.")
    code = fields.Text('QWeb Code')

    # ------------------------------------------------------------------
    # computes
    # ------------------------------------------------------------------
    @api.depends('block_type', 'table_field_id', 'builder_id.model_name')
    def _compute_source_model(self):
        for block in self:
            if block.block_type == 'table':
                block.source_model = block.table_field_id.relation or False
            else:
                block.source_model = block.builder_id.model_name or False

    @api.depends('block_type', 'text', 'item_ids', 'item_ids.field_id',
                 'item_ids.label', 'table_field_id', 'image_source', 'height')
    def _compute_summary(self):
        for block in self:
            kind = block.block_type
            if kind in ('heading', 'text', 'signature'):
                summary = (block.text or '').strip().replace('\n', ' / ')[:90]
            elif kind in ('fields', 'totals'):
                summary = ', '.join(item._label() for item in block.item_ids[:5])
                if len(block.item_ids) > 5:
                    summary += ', …'
            elif kind == 'table':
                summary = '%s → %s' % (
                    block.table_field_id.field_description or '?',
                    ', '.join(item._label() for item in block.item_ids[:4]))
            elif kind == 'twocol':
                summary = '%s | %s' % (
                    _('Company logo') if block.show_logo else (block.text or '').replace('\n', ' / ')[:40],
                    (block.text_right or '').replace('\n', ' / ')[:60])
            elif kind == 'image':
                summary = {'field': _('Record image'), 'company': _('Company logo')}.get(
                    block.image_source, _('Uploaded image'))
            elif kind == 'spacer':
                summary = '%s px' % block.height
            elif kind == 'code':
                summary = (block.code or '').strip().replace('\n', ' ')[:60]
            else:
                summary = ''
            block.summary = summary

    @api.onchange('table_field_id')
    def _onchange_table_field_id(self):
        self.item_ids = [(5, 0, 0)]

    # ------------------------------------------------------------------
    # rendering helpers
    # ------------------------------------------------------------------
    def _error(self, msg):
        label = dict(self._fields['block_type'].selection).get(self.block_type, '')
        return UserError(_('Block "%(type)s" (position %(seq)s): %(msg)s',
                           type=label, seq=self.sequence, msg=msg))

    def _items(self):
        return self.item_ids.sorted(key=lambda i: (i.sequence, i._origin.id or 0))

    def _value(self, item, root):
        return self.builder_id._value_node(root, item._path(), self.source_model)

    def _style(self, extra=None):
        """Inline style shared by all blocks."""
        self.ensure_one()
        safe = self.builder_id._safe_color
        parts = []
        if self.align and self.align != 'left':
            parts.append('text-align:%s' % self.align)
        if self.font_size:
            parts.append('font-size:%dpt' % self.font_size)
        if self.bold:
            parts.append('font-weight:bold')
        if safe(self.color):
            parts.append('color:%s' % safe(self.color))
        if safe(self.background):
            parts.append('background-color:%s;padding:6px 10px' % safe(self.background))
        if self.border_bottom:
            accent = safe(self.builder_id.primary_color) or '#714B67'
            parts.append('border-bottom:2px solid %s;padding-bottom:4px' % accent)
        parts.append('margin:%dpx 0 %dpx 0' % (self.margin_top or 0, self.margin_bottom or 0))
        if extra:
            parts.append(extra)
        return ';'.join(parts)

    def _render_block(self):
        self.ensure_one()
        xml = getattr(self, '_render_%s' % self.block_type)()
        if self.condition and self.condition.strip():
            xml = '<t t-if=%s>%s</t>' % (quoteattr(self.condition.strip()), xml)
        return xml

    # ------------------------------------------------------------------
    # block renderers
    # ------------------------------------------------------------------
    def _render_heading(self):
        level = self.heading_level or '2'
        accent = None
        if not self.builder_id._safe_color(self.color):
            accent = 'color:%s' % (self.builder_id._safe_color(
                self.builder_id.heading_color if self.builder_id.use_custom_colors
                else self.builder_id.primary_color) or '#714B67')
        return '<h%s style=%s>%s</h%s>' % (
            level, quoteattr(self._style(accent)),
            self.builder_id._text_to_xml(self.text), level)

    def _render_text(self):
        return '<div style=%s>%s</div>' % (
            quoteattr(self._style()), self.builder_id._text_to_xml(self.text))

    def _render_fields(self):
        items = self._items()
        if not items:
            raise self._error(_("add at least one field."))
        cols = int(self.columns or 2)
        width = 100.0 / cols
        rows = []
        for start in range(0, len(items), cols):
            chunk = items[start:start + cols]
            cells = ''.join(
                '<td style="width:%.2f%%;padding:3px 8px 3px 0;vertical-align:top;">'
                '<strong>%s:</strong> %s</td>' % (width, escape(it._label()), self._value(it, 'o'))
                for it in chunk)
            cells += '<td></td>' * (cols - len(chunk))
            rows.append('<tr>%s</tr>' % cells)
        return '<table style=%s><tbody>%s</tbody></table>' % (
            quoteattr(self._style('width:100%;border-collapse:collapse')), ''.join(rows))

    def _render_table(self):
        if not self.table_field_id:
            raise self._error(_("choose where the rows come from."))
        items = self._items()
        if not items:
            raise self._error(_("add at least one column."))
        builder = self.builder_id
        row_model = self.source_model
        heads = ['<th style="width:4%;text-align:left;">#</th>'] if self.show_index else []
        cells = ['<td t-out="row_index + 1"/>'] if self.show_index else []
        footer = ['<td></td>'] if self.show_index else []
        has_total = False
        for pos, it in enumerate(items):
            field = builder._resolve_field(row_model, it._path())
            align = it._align(field)
            width = 'width:%d%%;' % it.width if it.width else ''
            heads.append('<th style="%stext-align:%s;">%s</th>' % (
                width, align, escape(it._label())))
            cells.append('<td style="text-align:%s;">%s</td>' % (align, self._value(it, 'row')))
            if it.sum_total:
                has_total = True
                footer.append('<td style="text-align:%s;font-weight:bold;">%s</td>' % (
                    align, self._sum_node(it, field)))
            elif pos == 0:
                footer.append('<td style="font-weight:bold;">%s</td>' % escape(_('Total')))
            else:
                footer.append('<td></td>')
        table = (
            '<table class="rb-table%(striped)s" style=%(style)s>'
            '<thead><tr>%(head)s</tr></thead>'
            '<tbody><tr t-foreach=%(rows)s t-as="row">%(cells)s</tr></tbody>'
            '%(tfoot)s</table>'
        ) % {
            'striped': ' rb-striped' if self.striped else '',
            'style': quoteattr(self._style()),
            'head': ''.join(heads),
            'rows': quoteattr('o.%s' % self.table_field_id.name),
            'cells': ''.join(cells),
            'tfoot': '<tfoot><tr>%s</tr></tfoot>' % ''.join(footer) if has_total else '',
        }
        return table

    def _sum_node(self, item, field):
        if field.type not in ('integer', 'float', 'monetary'):
            raise self._error(_("'%s' is not numeric, so it cannot be totalled.",
                                item._label()))
        expr = "sum(o.%s.mapped('%s'))" % (self.table_field_id.name, item._path())
        has_currency = 'currency_id' in self.env[self.builder_id.model_name]._fields
        if field.type == 'monetary' and has_currency:
            options = "{'widget': 'monetary', 'display_currency': o.currency_id}"
        elif field.type in ('float', 'monetary'):
            options = "{'widget': 'float', 'precision': 2}"
        else:
            return '<span t-out=%s/>' % quoteattr(expr)
        return '<span t-out=%s t-options=%s/>' % (quoteattr(expr), quoteattr(options))

    def _render_totals(self):
        items = self._items()
        if not items:
            raise self._error(_("add at least one field."))
        rows = []
        for pos, it in enumerate(items):
            last = pos == len(items) - 1
            style = 'font-weight:bold;border-top:1px solid #999999;' if last else ''
            rows.append(
                '<tr style=%s><td style="padding:3px 8px;">%s</td>'
                '<td style="padding:3px 8px;text-align:right;">%s</td></tr>' % (
                    quoteattr(style), escape(it._label()), self._value(it, 'o')))
        return '<div style=%s><table style="width:100%%;border-collapse:collapse;">' \
               '<tbody>%s</tbody></table></div>' % (
                   quoteattr(self._style('width:45%;margin-left:55%')), ''.join(rows))

    def _render_image(self):
        if self.image_width:
            size = 'width:%dpx;max-width:100%%;' % self.image_width
        else:
            size = 'max-height:90px;max-width:100%;'
        if self.image_source == 'company':
            img = ('<img t-if="company.logo" t-att-src="image_data_uri(company.logo)" '
                   'style=%s/>' % quoteattr(size))
        elif self.image_source == 'field':
            field = self.image_field_id
            if not field:
                raise self._error(_("choose the image field."))
            orm_field = self.builder_id._resolve_field(self.builder_id.model_name, field.name)
            if orm_field.type != 'binary':
                raise self._error(_("'%s' is not an image field.", field.field_description))
            img = '<img t-if=%s t-att-src=%s style=%s/>' % (
                quoteattr('o.%s' % field.name),
                quoteattr('image_data_uri(o.%s)' % field.name), quoteattr(size))
        else:
            if not self.image:
                raise self._error(_("upload an image."))
            img = '<img src=%s style=%s/>' % (
                quoteattr(image_data_uri(self.image)), quoteattr(size))
        return '<div style=%s>%s</div>' % (quoteattr(self._style()), img)

    def _render_twocol(self):
        builder = self.builder_id
        if self.show_logo:
            left = ('<img t-if="company.logo" t-att-src="image_data_uri(company.logo)" '
                    'style=%s/>' % quoteattr('max-height:%dpx;max-width:100%%;' % (self.height or 60)))
        else:
            left = builder._text_to_xml(self.text)
        right = builder._text_to_xml(self.text_right)
        return (
            '<table style=%s><tbody><tr>'
            '<td style="width:50%%;vertical-align:middle;">%s</td>'
            '<td style="width:50%%;vertical-align:middle;text-align:right;">%s</td>'
            '</tr></tbody></table>'
        ) % (quoteattr(self._style('width:100%;border-collapse:collapse')), left, right)

    def _render_signature(self):
        labels = [ln.strip() for ln in (self.text or '').splitlines() if ln.strip()] \
            or [_('Signature')]
        width = 100.0 / len(labels)
        cells = ''.join(
            '<td style="width:%.2f%%;padding:0 15px;text-align:center;">'
            '<div style="height:%dpx;border-bottom:1px solid #000000;"></div>'
            '<div style="padding-top:4px;">%s</div></td>' % (
                width, self.height or 40, escape(label))
            for label in labels)
        return '<table style=%s><tbody><tr>%s</tr></tbody></table>' % (
            quoteattr(self._style('width:100%;border-collapse:collapse')), cells)

    def _render_divider(self):
        color = self.builder_id._safe_color(self.color) or '#999999'
        return '<div style=%s></div>' % quoteattr(
            'border-top:1px solid %s;margin:%dpx 0 %dpx 0' % (
                color, self.margin_top or 0, self.margin_bottom or 0))

    def _render_spacer(self):
        return '<div style=%s></div>' % quoteattr('height:%dpx' % (self.height or 20))

    def _render_pagebreak(self):
        return '<div style="page-break-after:always;"></div>'

    def _render_code(self):
        code = (self.code or '').strip()
        if not code:
            raise self._error(_("write some QWeb code."))
        try:
            etree.fromstring('<t>%s</t>' % code)
        except etree.XMLSyntaxError as exc:
            raise self._error(_("invalid XML: %s", exc))
        return code
