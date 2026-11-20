import base64

from lxml import etree

from odoo import _, fields, models
from odoo.exceptions import UserError


class ReportLivePreview(models.Model):
    _inherit = 'report.builder'

    live_preview = fields.Text(string='Live report preview', compute='_compute_preview_placeholder')

    def _compute_preview_placeholder(self):
        for record in self:
            record.live_preview = False

    def _live_paper_geometry(self):
        base = self._base_paper_values()
        paper = dict(base, **self._banner_paper_values())
        if self.paper_format_source == 'existing':
            width = self.existing_paperformat_id.print_page_width
            height = self.existing_paperformat_id.print_page_height
        else:
            sizes = {'A4': (210, 297), 'A5': (148, 210), 'A3': (297, 420),
                     'Letter': (215.9, 279.4), 'Legal': (215.9, 355.6)}
            width, height = sizes[self.paper_format]
            if paper['orientation'] == 'Landscape':
                width, height = height, width
        margins = {key: float(paper[key]) for key in ('margin_top', 'margin_bottom', 'margin_left', 'margin_right')}
        if width <= margins['margin_left'] + margins['margin_right'] or height <= margins['margin_top'] + margins['margin_bottom']:
            raise UserError(_('The margins leave no printable area.'))
        return dict(margins, width=width, height=height, format=paper['format'],
                    orientation=paper['orientation'], header_spacing=paper['header_spacing'])

    def _render_live_pdf(self, sample):
        """Use the normal PDF engine with in-memory report/paper records."""
        paper_values = self._base_paper_values()
        paper_values.update(self._banner_paper_values())
        paper_values['name'] = 'Live preview: %s' % self.name
        paper = self.env['report.paperformat'].new(paper_values)
        report_values = {
            'name': self.name, 'model': self.model_name,
            'report_type': self.action_id.report_type if self.action_id else 'qweb-pdf',
            'report_name': self._report_key(), 'paperformat_id': paper,
            # Avoid external-ID lookup on the unsaved action.
            'xml_id': self.action_id.xml_id if self.action_id else '',
        }
        renderer = self.env['ir.actions.report'].with_context(debug=False)
        report = renderer.new(report_values, origin=self.action_id or None)
        arch = etree.fromstring(self._build_full_arch().encode())
        html = renderer._render_template(arch, {
            'doc_ids': sample.ids, 'doc_model': self.model_name, 'docs': sample,
            'report_type': 'pdf', 'is_preview': False, 'debug': False,
        }).decode()
        engine = renderer._get_pdf_engine(report)
        pdf, _ids = renderer._run_pdf_engine(
            engine, html, report_ref=report, landscape=self.env.context.get('landscape'))
        if not pdf.startswith(b'%PDF'):
            raise UserError(_('The report renderer did not return a PDF. Check the PDF engine settings.'))
        return base64.b64encode(self._finish_pdf(pdf)).decode()

    def preview_unsaved(self, changes=None):
        """Render an in-memory draft: never save edits or sync report records."""
        self.ensure_one()
        self._check_studio_access()
        self.check_access('read')
        if not self.exists():
            return {'pdf': '', 'error': _('Save the report before opening the live preview.')}
        # These values are never accepted as preview edits, even from a manually
        # crafted request. In particular do not expose publishing or ownership.
        protected = {'id', 'state', 'view_id', 'action_id', 'paperformat_id',
                     'generated_arch', 'live_preview', 'create_uid', 'write_uid',
                     'create_date', 'write_date', 'display_name'}
        values = {name: value for name, value in (changes or {}).items()
                  if name in self._fields and name not in protected
                  and not self._fields[name].readonly}
        # Explicitly seed unchanged child relations so Odoo links their inverse
        # builder_id to the in-memory parent as well (font/colour/model edits must
        # reach existing child blocks, not only newly edited ones).
        for name in ('block_ids', 'header_block_ids', 'footer_block_ids'):
            if name in self._fields and name not in values:
                values[name] = [(6, 0, self[name].ids)]
        try:
            draft = self.new(values, origin=self)
            if not draft.model_name:
                return {'pdf': '', 'error': _('Choose a report model first.')}
            model = self.env[draft.model_name]
            sample = model.browse(draft.preview_record_id).exists() if draft.preview_record_id else model.search([], limit=1)
            if not sample:
                return {'pdf': '', 'error': _('Choose or create a sample record to preview this report.')}
            sample.check_access('read')
            return {'pdf': draft._render_live_pdf(sample),
                    'paper': draft._live_paper_geometry(), 'filename': draft._download_filename(sample), 'error': False}
        except Exception as exc:
            # An unfinished condition/XML fragment should not take down the form.
            return {'pdf': '', 'error': str(exc) or _('The draft could not be rendered. Check the edited content.')}
