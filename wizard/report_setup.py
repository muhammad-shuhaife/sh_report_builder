from odoo import _, api, fields, models
from odoo.exceptions import UserError
from ..models.report_design import PAGE_DESIGNS, LINE_DESIGNS, PRESETS
from ..models.body_patterns import BODY_DESIGNS


class ReportSetup(models.TransientModel):
    _name = 'report.builder.setup'
    _description = 'Report Studio Configuration'

    name = fields.Char('Report name', required=True, default='My report')
    preset = fields.Selection(selection='_preset_choices', required=True, default='custom', string='Report template')
    model_id = fields.Many2one('ir.model', string='Applies to', required=True,
                              domain=[('transient', '=', False)])
    start_content = fields.Selection([('starter', 'Starter layout'), ('blank', 'Blank report')], default='starter', required=True)
    page_design = fields.Selection([('none', 'Blank page')] + PAGE_DESIGNS, default='classic', required=True)
    line_design = fields.Selection(LINE_DESIGNS, default='plain', required=True)
    body_design = fields.Selection([('none','Plain body')] + BODY_DESIGNS, default='none',required=True,string='In-page design')
    body_design_color = fields.Char('Texture colour',default='#714B67')
    body_design_opacity = fields.Integer('Texture opacity (%)',default=18)
    body_design_watermark = fields.Char('Watermark text',default=lambda self:self.env.company.name)
    primary_color = fields.Char('Accent colour', default='#714B67', required=True)
    branding = fields.Selection([('design', 'Company logo and designed header/footer'),
                                 ('image', 'Upload header/footer images in the editor'),
                                 ('company', 'Odoo company layout')], default='design', required=True)
    paper_source = fields.Selection([('custom', 'A4 portrait'), ('existing', 'Existing paper format')], default='custom', required=True)
    existing_paperformat_id = fields.Many2one('report.paperformat', string='Existing paper format')

    @api.model
    def _preset_choices(self):
        available = set(self.env['ir.model'].search([('model', 'in', [m for m, label in PRESETS])]).mapped('model'))
        return [('custom', 'Create my own')] + [(m, label) for m, label in PRESETS if m in available]

    @api.onchange('preset')
    def _onchange_preset(self):
        if self.preset != 'custom':
            self.model_id = self.env['ir.model']._get(self.preset)
            self.name = dict(PRESETS).get(self.preset, 'My report')

    def action_create_report(self):
        self.ensure_one()
        self.env['report.builder']._check_studio_access()
        if self.model_id.transient:
            raise UserError(_('Select a persistent business model.'))
        if self.preset != 'custom' and self.model_id.model != self.preset:
            raise UserError(_('The model must match the selected report template.'))
        if self.paper_source == 'existing' and not self.existing_paperformat_id:
            raise UserError(_('Select an existing paper format.'))
        if not 0 <= self.body_design_opacity <= 100:
            raise UserError(_('Texture opacity must be between 0 and 100 percent.'))
        vals = {'body_design': self.body_design, 'body_design_color': self.body_design_color,
                'body_design_opacity': self.body_design_opacity, 'body_design_watermark': self.body_design_watermark,
                'name': self.name, 'model_id': self.model_id.id,
                'page_design': self.page_design if self.branding != 'company' else 'none',
                'line_design': self.line_design,
                'primary_color': self.primary_color, 'layout': 'custom',
                'header_mode': self.branding if self.branding != 'company' else 'none',
                'footer_mode': self.branding if self.branding != 'company' else 'none',
                'paper_format_source': self.paper_source,
                'existing_paperformat_id': self.existing_paperformat_id.id,
                'margin_top': 45, 'margin_bottom': 25, 'header_spacing': 5}
        report = self.env['report.builder'].create(vals)
        if self.start_content == 'starter':
            report.action_load_starter()
        if self.branding == 'design':
            report.action_load_header_footer()
        elif self.branding == 'company':
            report.layout = 'company'
            report._onchange_layout()
        return {'type': 'ir.actions.act_window', 'res_model': 'report.builder',
                'res_id': report.id, 'view_mode': 'form',
                'views': [(False, 'form')], 'target': 'current',
                'name': report.name}
