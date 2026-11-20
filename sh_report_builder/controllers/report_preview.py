from odoo.http import Controller, request, route
from odoo.http.stream import content_disposition
from werkzeug.exceptions import NotFound


class ReportBuilderPreview(Controller):
    @route('/sh_report_builder/pdf/<int:design_id>/<int:sample_id>', type='http', auth='user', readonly=True)
    def pdf_preview(self, design_id, sample_id, **kwargs):
        design = request.env['report.builder'].browse(design_id).exists()
        if not design:
            raise NotFound()
        design.check_access('read')
        sample = request.env[design.model_name].browse(sample_id).exists()
        if not sample or not design.action_id:
            raise NotFound()
        sample.check_access('read')
        pdf, _kind = request.env['ir.actions.report']._render_qweb_pdf(design.action_id, sample.ids)
        return request.make_response(pdf, headers=[
            ('Content-Type', 'application/pdf'),
            ('Content-Disposition', content_disposition(design._download_filename(sample), disposition_type='inline')),
            ('Cache-Control', 'no-store'),
        ])
