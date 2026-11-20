"""Output controls shared by normal PDF downloads and unsaved PDF previews."""
import base64
from io import BytesIO
from xml.sax.saxutils import quoteattr

from lxml import etree
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.pdf import PdfReader, PdfWriter
from odoo.tools.safe_eval import safe_eval, time
from .sh_report_builder import TOKEN_RE


class ReportOutput(models.Model):
    _inherit = 'report.builder'

    header_repeat = fields.Selection([('every', 'Every page'), ('first', 'First page only')],
                                    default='every', required=True, string='Show header on')
    footer_repeat = fields.Selection([('every', 'Every page'), ('last', 'Last page only'),
                                     ('first', 'First page only')],
                                    default='every', required=True, string='Show footer on')
    page_number_display = fields.Selection([
        ('existing', 'Use existing header/footer blocks'), ('none', 'No page numbers'),
        ('page', 'Page 1'), ('total', 'Page 1 of 3')], default='existing', required=True,
        string='Page numbers')
    page_number_position = fields.Selection([
        ('top_left', 'Top left'), ('top_center', 'Top centre'), ('top_right', 'Top right'),
        ('bottom_left', 'Bottom left'), ('bottom_center', 'Bottom centre'),
        ('bottom_right', 'Bottom right')], default='bottom_right', required=True,
        string='Number position')
    page_number_inset = fields.Integer('Distance from page edge (mm)', default=8)
    page_number_size = fields.Integer('Page number font size (pt)', default=9)
    background_mode = fields.Selection([('watermark', 'Watermark behind content'),
                                        ('decoration', 'Decorative background')],
                                       default='watermark', required=True, string='Image treatment')
    background_scale = fields.Integer('Watermark width (%)', default=70)
    background_position = fields.Selection([('center', 'Centre'), ('top', 'Top'), ('bottom', 'Bottom')],
                                          default='center', required=True, string='Watermark position')

    download_name_preview = fields.Char('Download filename example', compute='_compute_download_name')

    def _print_name_expr(self):
        self.ensure_one()
        pattern = (self.print_name or self.name or 'Report').strip()
        if pattern.lower().endswith('.pdf'):
            pattern = pattern[:-4]
        parts, pos = [], 0
        for match in TOKEN_RE.finditer(pattern):
            parts.append(repr(pattern[pos:match.start()]))
            path = match.group(1)
            if path == 'date':
                parts.append("time.strftime('%Y-%m-%d')")
            elif path == 'report_name':
                parts.append(repr(self.name or 'Report'))
            else:
                field = self._resolve_field(self.model_name, path)
                parts.append("str(object.%s%s or '')" % (path, '.display_name' if field.type == 'many2one' else ''))
            pos = match.end()
        parts.append(repr(pattern[pos:]))
        expr = '(' + ' + '.join(parts) + ')'
        for char in '<>:"/\\|?*\n\r\t':
            expr += '.replace(%r, %r)' % (char, '-' if char not in '\n\r\t' else ' ')
        return '(' + expr + ".strip().strip('.')[:180] or 'Report')"

    def _download_filename(self, sample):
        return safe_eval(self._print_name_expr(), {'object': sample, 'time': time}) + '.pdf'

    @api.depends('print_name', 'name', 'model_id', 'preview_record_id')
    def _compute_download_name(self):
        for rec in self:
            try:
                sample = rec.env[rec.model_name].browse(rec.preview_record_id).exists() if rec.preview_record_id else rec.env[rec.model_name].search([], limit=1)
                rec.download_name_preview = rec._download_filename(sample) if sample else _('Choose a preview record to see the filename.')
            except (UserError, ValueError, KeyError, AttributeError):
                rec.download_name_preview = _('Check the filename placeholders against this report model.')

    def action_download_pdf(self):
        self.ensure_one()
        self._sync_records(bind=self.state == 'published')
        sample = self.env[self.model_name].browse(self.preview_record_id).exists() if self.preview_record_id else self.env[self.model_name].search([], limit=1)
        if not sample:
            raise UserError(_('Choose or create a preview record first.'))
        sample.check_access('read')
        return self.action_id.report_action(sample)

    def action_preview_pdf(self):
        action = self._preview('pdf')
        sample_id = int(action['url'].rsplit('/', 1)[1])
        action['url'] = '/sh_report_builder/pdf/%s/%s' % (self.id, sample_id)
        return action

    @api.constrains('page_number_inset', 'page_number_size', 'background_scale', 'background_opacity', 'background_saturation')
    def _check_output_controls(self):
        for rec in self:
            if not 0 <= rec.background_saturation <= 200:
                raise UserError(_('Background saturation must be between 0 and 200 percent.'))
            if not 0 <= rec.background_opacity <= 100 or not 1 <= rec.background_scale <= 100:
                raise UserError(_('Use opacity from 0 to 100 and watermark width from 1 to 100 percent.'))
            if rec.page_number_inset < 2 or not 5 <= rec.page_number_size <= 30:
                raise UserError(_('Page numbers need an inset of at least 2 mm and a font size from 5 to 30 pt.'))

    def _text_to_xml(self, text):
        if self.layout != 'company' and self.page_number_display != 'existing' and any(
                match.group(1) in ('page', 'topage') for match in TOKEN_RE.finditer(text or '')):
            return ''
        return super()._text_to_xml(text)

    def _zone_xml(self, zone):
        xml = super()._zone_xml(zone)
        repeat = self['%s_repeat' % zone]
        if not xml or repeat == 'every':
            return xml
        node = etree.fromstring(xml.encode())
        marker = 'rb-once-%s' % zone
        node.set('class', node.get('class', '') + ' ' + marker)
        # wkhtmltopdf provides page variables on each header/footer document URL.
        # Hide content, preserving the configured page margin and banner width.
        script = etree.SubElement(node, 'script', {'type': 'text/javascript'})
        script.text = '''(function(){function apply(){var vars={},parts=location.search.substring(1).split(String.fromCharCode(38));
for(var i=0;i<parts.length;i++){var pair=parts[i].split('=');vars[pair[0]]=decodeURIComponent(pair[1]||'');}
var page=parseInt(vars.sitepage||vars.page||'1',10),total=parseInt(vars.sitepages||vars.topage||'1',10);
var keep=CONDITION;var nodes=document.getElementsByClassName('MARKER');
for(var j=0;j<nodes.length;j++){nodes[j].style.visibility=keep?'visible':'hidden';}}
if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',apply);}else{apply();}
window.addEventListener('load',apply);})();'''.replace('CONDITION', 'page===1' if repeat == 'first' else 'page===total').replace('MARKER', marker)
        return etree.tostring(node, encoding='unicode')

    def _watermark_xml(self):
        if not self.use_background_image or not self.background_image or self.background_mode != 'watermark':
            return ''
        if not 1 <= self.background_scale <= 100:
            raise UserError(_('Watermark width must be between 1 and 100 percent.'))
        position = {'top': 'center top', 'center': 'center center', 'bottom': 'center bottom'}[self.background_position]
        paper = self._live_paper_geometry()
        width = paper['width'] - paper['margin_left'] - paper['margin_right']
        height = paper['height'] - paper['margin_top'] - paper['margin_bottom']
        style = ('position:fixed;top:0;left:0;width:%smm;height:%smm;z-index:0;pointer-events:none;'
                 'background-image:url("%s");background-repeat:no-repeat;background-size:%s%% auto;'
                 'background-position:%s;') % (width, height, self._background_data_uri(), self.background_scale, position)
        return '<div t-if="report_type != \'pdf\'" class="rb-watermark" aria-hidden="true" style=%s></div>' % quoteattr(style)

    def _watermark_rect(self, page_width, page_height, image_width, image_height):
        """Position in PDF points; independent of HTML DPI and smart shrinking."""
        paper = self._base_paper_values()
        mm = 72 / 25.4
        left, right = paper['margin_left'] * mm, page_width - paper['margin_right'] * mm
        bottom, top = paper['margin_bottom'] * mm, page_height - paper['margin_top'] * mm
        available_width, available_height = right - left, top - bottom
        if min(available_width, available_height) <= 0 or not 1 <= self.background_scale <= 100:
            raise UserError(_('Check the watermark width and paper margins.'))
        scale = min(available_width * self.background_scale / 100 / image_width, available_height / image_height)
        width, height = image_width * scale, image_height * scale
        x = left + (available_width - width) / 2
        if self.background_position == 'top':
            y = top - height
        elif self.background_position == 'bottom':
            y = bottom
        else:
            y = bottom + (available_height - height) / 2
        return x, y, width, height

    def _finish_pdf(self, pdf):
        """Place watermarks and page numbers using the actual PDF page geometry."""
        watermark = self.use_background_image and self.background_image and self.background_mode == 'watermark'
        numbering = self.layout != 'company' and self.page_number_display not in ('existing', 'none')
        if not watermark and not numbering:
            return pdf
        if numbering and (self.page_number_inset < 2 or not 5 <= self.page_number_size <= 30):
            raise UserError(_('Check the page number inset and font size.'))
        image = None
        if watermark:
            image = ImageReader(BytesIO(base64.b64decode(self._background_data_uri().split(',', 1)[1])))
        reader = PdfReader(BytesIO(pdf))
        writer = PdfWriter()
        total = len(reader.pages)
        inset = self.page_number_inset * 72 / 25.4
        for number, page in enumerate(reader.pages, 1):
            width, height = float(page.mediabox.width), float(page.mediabox.height)
            if image:
                x, y, image_width, image_height = self._watermark_rect(width, height, *image.getSize())
                stream = BytesIO()
                layer = canvas.Canvas(stream, pagesize=(width, height))
                layer.drawImage(image, x, y, width=image_width, height=image_height, mask='auto')
                layer.save()
                underlay = PdfReader(BytesIO(stream.getvalue())).pages[0]
                underlay.merge_page(page)
                page = underlay
            if numbering:
                if inset * 2 >= min(width, height):
                    raise UserError(_('The page number inset is too large for this paper format.'))
                stream = BytesIO()
                layer = canvas.Canvas(stream, pagesize=(width, height))
                layer.setFont('Helvetica', self.page_number_size)
                layer.setFillColorRGB(.3, .3, .3)
                text = 'Page %s' % number
                if self.page_number_display == 'total':
                    text += ' of %s' % total
                edge, align = self.page_number_position.split('_')
                y = height - inset - self.page_number_size if edge == 'top' else inset
                if align == 'left':
                    layer.drawString(inset, y, text)
                elif align == 'center':
                    layer.drawCentredString(width / 2, y, text)
                else:
                    layer.drawRightString(width - inset, y, text)
                layer.save()
                page.merge_page(PdfReader(BytesIO(stream.getvalue())).pages[0])
            writer.add_page(page)
        result = BytesIO()
        writer.write(result)
        return result.getvalue()


class ReportOutputAction(models.Model):
    _inherit = 'ir.actions.report'

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        pdf, kind = super()._render_qweb_pdf(report_ref, res_ids=res_ids, data=data)
        if kind == 'pdf':
            report = self._get_report(report_ref)
            design = self.env['report.builder'].sudo().search([('action_id', '=', report.id)], limit=1)
            if design:
                pdf = design._finish_pdf(pdf)
        return pdf, kind
