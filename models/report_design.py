from io import BytesIO
from xml.sax.saxutils import quoteattr

from lxml import etree
from PIL import Image

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import file_open
from odoo.tools.image import image_data_uri
from .body_patterns import BODY_DESIGNS, TILED

PAGE_DESIGNS = [
    ('classic', 'Classic letterhead'), ('circle', 'Circular corners'),
    ('wave', 'Wave letterhead'), ('ribbon', 'Ribbon header'),
    ('angular', 'Angled edges'), ('contour', 'Contour lines'),
    ('duo', 'Studio · Dual band'), ('corner', 'Studio · Corner blocks'),
    ('rail', 'Studio · Side stripe'), ('frame', 'Studio · Fine frame'),
    ('horizon', 'Studio · Horizon'), ('grid', 'Studio · Technical grid'),
    ('arches', 'Studio · Arches'), ('facets', 'Studio · Crystal facets'),
    ('orbit', 'Studio · Orbit'), ('chevron', 'Studio · Chevron'),
    ('steps', 'Studio · Stepped edge'), ('mesh', 'Studio · Diagonal mesh'),
]
LINE_DESIGNS = [('legacy', 'Current / block styling'), ('plain', 'Plain lines'),
                ('ruled', 'Accent rules'), ('boxed', 'Boxed grid'),
                ('striped', 'Striped rows'), ('dark', 'Dark header'),
                ('accent', 'Colour header'), ('minimal', 'Airy minimal'),
                ('ledger', 'Ledger columns'), ('soft', 'Soft lavender'),
                ('double', 'Double rules'), ('banded', 'Alternating bands'),
                ('cards', 'Separated rows')]
PRESETS = [('sale.order', 'Quotation / Sales Order'), ('account.move', 'Invoice'),
           ('purchase.order', 'Purchase Order'), ('stock.picking', 'Delivery Slip'),
           ('res.partner', 'Contact Profile')]


class ReportDesign(models.Model):
    _inherit = 'report.builder'

    page_design = fields.Selection([('none', 'No gallery design')] + PAGE_DESIGNS,
                                   default='none', required=True)
    line_design = fields.Selection(LINE_DESIGNS, default='legacy', required=True)

    @api.onchange('page_design')
    def _onchange_page_design(self):
        for report in self:
            if report.page_design != 'none':
                report.layout = 'custom'

    @api.model
    def _check_studio_access(self):
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_('Only Settings administrators can use Report Studio.'))

    @api.model
    def studio_data(self):
        self._check_studio_access()
        reports = self.search_read([], ['name', 'model_name', 'state', 'page_design'], limit=100)
        return {'designs': [{'key': key, 'name': name,
                             'preview': '/sh_report_builder/static/gallery/%s.png' % key}
                            for key, name in PAGE_DESIGNS],
                'textures': [{'key': key, 'name': name, 'preview': '/sh_report_builder/static/gallery/body_%s.png' % key,
                              'texture': self.new({'body_design': key, 'body_design_opacity': 100,
                                                   'body_design_color': '#714B67',
                                                   'body_design_watermark': 'YOUR COMPANY'})._body_texture_uri(),
                              'tiled': key in TILED} for key,name in BODY_DESIGNS],
                'lines': [{'key': key, 'name': name} for key, name in LINE_DESIGNS if key != 'legacy'],
                'reports': reports}

    @api.model
    def action_configure_design(self, page='classic', line='plain', body='none', opacity=18):
        self._check_studio_access()
        if page not in dict(PAGE_DESIGNS) and page != 'none':
            raise UserError(_('Choose a valid page design.'))
        if line not in dict(LINE_DESIGNS):
            raise UserError(_('Choose a valid table design.'))
        if body not in dict(BODY_DESIGNS) and body != 'none':
            raise UserError(_('Choose a valid in-page design.'))
        if not isinstance(opacity, (int, float)) or not 0 <= opacity <= 100:
            raise UserError(_('Texture opacity must be between 0 and 100 percent.'))
        return {'type': 'ir.actions.act_window', 'name': _('Configure your report'),
                'res_model': 'report.builder.setup', 'view_mode': 'form',
                'views': [(False, 'form')], 'target': 'new',
                'context': {'default_page_design': page, 'default_line_design': line, 'default_body_design': body, 'default_body_design_opacity': int(opacity),
                            'default_start_content': 'blank' if page == 'none' else 'starter'}}

    @api.model
    def studio_preview(self, page='classic', line='plain', body='none', opacity=18):
        """Compose every selected style with the same assets/CSS as final reports."""
        self._check_studio_access()
        # Reuse the configuration validation; no records are created.
        self.action_configure_design(page, line, body, opacity)
        draft = self.new({'page_design': page, 'line_design': line,
                          'body_design': body, 'body_design_opacity': int(opacity),
                          'primary_color': '#714B67', 'body_design_color': '#714B67',
                          'body_design_watermark': 'YOUR COMPANY', 'layout': 'custom'})
        css = draft._build_css()
        header = draft._design_background('header') if page != 'none' else ''
        footer = draft._design_background('footer') if page != 'none' else ''
        html = '''<!doctype html><html><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<style>html{background:#eeebf2}body{margin:12px;font:13px Arial,sans-serif;color:#302838}
.paper{position:relative;box-sizing:border-box;max-width:794px;min-height:1050px;margin:auto;background:white;box-shadow:0 4px 20px #30283815}
header,footer{position:relative;height:140px;box-sizing:border-box;padding:32px}
.art{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
.brand{display:flex;justify-content:space-between;gap:20px;position:relative;z-index:3}
.brand b{font-size:22px;color:#714B67}.brand small{text-align:right;line-height:1.6}
.rb-report{box-sizing:border-box;min-height:770px;padding:30px 32px}
h1{font-size:28px;margin:20px 0}p{line-height:1.7}.meta{display:flex;justify-content:space-between;margin:25px 0}
table{font-size:12px}th,td{text-align:left}th+th,td+td{text-align:right}
.total{margin:25px 0 65px auto;width:45%;border-top:2px solid #714B67;padding:12px 0;text-align:right}
footer{font-size:11px;text-align:center;color:#635a68;padding-top:70px}
.sample{font-size:10px;letter-spacing:1px;text-transform:uppercase;color:#81728a}
CSS</style></head><body><div class="paper"><header>HEADER
<div class="brand"><b>Your company</b><small>Business address<br/>City, Country<br/>hello@example.com</small></div>
</header><main class="rb-report"><span class="sample">Illustrative report sample</span>
<h1>Quotation / SO00042</h1><p><b>Acme Corporation</b><br/>Customer address<br/>City, Country</p>
<div class="meta"><span><b>Quotation date</b><br/>18 Nov 2026</span><span><b>Valid until</b><br/>18 Dec 2026</span></div>
<table class="rb-table rb-striped"><thead><tr><th>Description</th><th>Qty</th><th>Unit price</th><th>Amount</th></tr></thead>
<tbody><tr><td>Office desk</td><td>2</td><td>240.00</td><td>480.00</td></tr>
<tr><td>Task chair</td><td>4</td><td>80.00</td><td>320.00</td></tr>
<tr><td>Storage unit</td><td>1</td><td>200.00</td><td>200.00</td></tr>
<tr><td>Installation service</td><td>1</td><td>100.00</td><td>100.00</td></tr></tbody></table>
<div class="total">Untaxed amount: $1,100.00<br/>Tax: $165.00<br/><br/><b>Total: $1,265.00</b></div>
<p>Payment terms: 30 days<br/>Thank you for your business.</p></main>
<footer>FOOTER<div style="position:relative;z-index:3">hello@example.com · +1 555 555 5556<br/>Page 1 / 1</div></footer></div></body></html>'''
        return html.replace('CSS', css).replace('HEADER', '<img class="art" alt="" src=%s/>' % quoteattr(header) if header else '').replace('FOOTER', '<img class="art" alt="" src=%s/>' % quoteattr(footer) if footer else '')

    def action_open_gallery(self):
        self._check_studio_access()
        return {'type': 'ir.actions.client', 'tag': 'sh_report_builder.studio',
                'params': {'gallery': True}, 'name': _('Report Studio'), 'display_name': _('Report Studio')}

    def _design_background(self, zone):
        with file_open('sh_report_builder/static/gallery/%s_%s.png' % (self.page_design, zone), 'rb') as stream:
            with Image.open(stream) as source:
                alpha = source.convert('RGBA').getchannel('A').point(lambda value: min(value, 48))
        color = self._safe_color(self.primary_color) or '#714B67'
        # PIL accepts CSS names and hex colours; fall back for unsupported CSS forms.
        try:
            image = Image.new('RGBA', alpha.size, color)
        except ValueError:
            image = Image.new('RGBA', alpha.size, '#714B67')
        image.putalpha(alpha)
        output = BytesIO()
        image.save(output, format='PNG')
        return image_data_uri(output.getvalue())

    def _zone_xml(self, zone):
        xml = super()._zone_xml(zone)
        if self.page_design == 'none' or self.layout != 'custom' or not xml:
            return xml
        # Page artwork is cosmetic: retain the original header/footer element,
        # its contents, dimensions and PDF paper format. The only added node is
        # absolutely positioned, so it cannot push or cover report body content.
        node = etree.fromstring(xml.encode())
        node.set('style', node.get('style', '').rstrip(';') + ';position:relative;')
        etree.SubElement(node, 'img', {
            'src': self._design_background(zone),
            'alt': '',
            'style': 'position:absolute;top:0;left:0;width:100%;height:100%;'
                     'z-index:2;pointer-events:none;',
        })
        return etree.tostring(node, encoding='unicode')

    def _build_css(self):
        css = super()._build_css()
        if self.line_design == 'legacy':
            return css
        color = self._safe_color(self.primary_color) or '#714B67'
        base = '.rb-report table.rb-table'
        css += (base + ' th{background:transparent;color:inherit;border:0;}' +
                base + ' td{border:0;}' + base + '.rb-striped tbody tr:nth-child(even) td{background:transparent;}' +
                base + ' tfoot td{border-top:1px solid #ccc;}')
        styles = {
            'plain': ' th{border-bottom:1px solid #999;}',
            'ruled': ' th{border-top:1px solid COLOR;border-bottom:1px solid COLOR;color:COLOR;}| td{border-bottom:1px solid #ded9df;}',
            'boxed': ' th{border:1px solid #aaa;}| td{border:1px solid #ccc;}',
            'striped': ' th{border-bottom:1px solid #999;}| tbody tr:nth-child(odd) td{background:#eceaec;}',
            'dark': ' th{background:#17131b;color:white;}| td{border-right:1px solid #eee;border-bottom:1px solid #eee;}',
            'accent': ' th{background:COLOR;color:white;}| td{border-bottom:1px solid #e3dfe6;}',
            'minimal': ' th{color:COLOR;font-size:90%;border-bottom:2px solid COLOR;padding:12px 8px;}| td{padding:12px 8px;}',
            'ledger': ' th{color:COLOR;border-bottom:2px solid COLOR;}| td+td{border-left:1px solid #ddd;}| tbody tr:last-child td{border-bottom:1px solid COLOR;}',
            'soft': ' th{background:#f1eaf6;color:COLOR;border-bottom:2px solid COLOR;}| td{border-bottom:1px solid #e8e1ed;}',
            'double': ' th{color:COLOR;border-top:3px double COLOR;border-bottom:3px double COLOR;}| td{border-bottom:1px solid #eee;}| tbody tr:last-child td{border-bottom:3px double COLOR;}',
            'banded': ' th{background:COLOR;color:white;}| tbody tr:nth-child(odd) td{background:#f1edf5;}| td{border-bottom:2px solid white;}',
            'cards': ' th{color:COLOR;border-bottom:2px solid COLOR;}| td{background:#f5f4f7;border-top:5px solid white;border-bottom:5px solid white;padding:10px 8px;}',
        }
        css += ''.join(base + rule for rule in styles[self.line_design].replace('COLOR', color).split('|'))
        return css
