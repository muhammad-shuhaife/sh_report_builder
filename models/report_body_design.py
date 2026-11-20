from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools import file_open
from odoo.tools.image import image_data_uri
from .body_patterns import BODY_DESIGNS, TILED, make_texture


class ReportBodyDesign(models.Model):
    _inherit = 'report.builder'

    body_design = fields.Selection([('none','Plain body')] + BODY_DESIGNS,
                                   string='In-page design',default='none',required=True)
    body_design_color = fields.Char('Texture colour',default='#714B67')
    body_design_opacity = fields.Integer('Texture opacity (%)',default=18)
    body_design_watermark = fields.Char('Watermark text',default=lambda self:self.env.company.name)

    def _body_texture_uri(self):
        self.ensure_one()
        if not 0 <= self.body_design_opacity <= 100:
            raise UserError(_('Texture opacity must be between 0 and 100 percent.'))
        font_bytes=None
        if self.body_design=='watermark':
            with file_open('web/static/fonts/sign/NotoSans-Regular.ttf','rb') as stream:
                font_bytes=stream.read()
        color=self._safe_color(self.body_design_color) or '#714B67'
        try:
            data=make_texture(self.body_design,color,self.body_design_opacity,
                              self.body_design_watermark or self.env.company.name,font_bytes)
        except ValueError as exc:
            raise UserError(_('Choose a valid texture colour and opacity.')) from exc
        return image_data_uri(data)

    def _build_css(self):
        css=super()._build_css()
        if self.body_design=='none':
            return css
        images=['url("%s")' % self._body_texture_uri()]
        sizes=['96px 96px' if self.body_design in TILED else '100% 100%']
        repeats=['repeat' if self.body_design in TILED else 'no-repeat']
        if self.use_background_image and self.background_image and self.background_mode != 'watermark':
            images.append('url("%s")' % self._background_data_uri())
            sizes.append(self.background_fit if self.background_fit in ('cover','contain') else 'auto')
            repeats.append('repeat' if self.background_fit=='repeat' else 'no-repeat')
        return css+('.rb-report{background-image:%s;background-size:%s;'
                    'background-repeat:%s;background-position:center center;}') % (
                        ','.join(images),','.join(sizes),','.join(repeats))
