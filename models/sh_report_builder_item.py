from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ReportBuilderItem(models.Model):
    _name = 'report.builder.item'
    _description = 'Report Design Field / Column'
    _order = 'sequence, id'

    block_id = fields.Many2one('report.builder.block', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    source_model = fields.Char(related='block_id.source_model')
    field_id = fields.Many2one('ir.model.fields', string='Field', required=True,
                               ondelete='cascade')
    field_type = fields.Selection(related='field_id.ttype')
    field_relation = fields.Char(related='field_id.relation')
    sub_field_id = fields.Many2one(
        'ir.model.fields', string='Sub-field', ondelete='cascade',
        help="For relations: print a field of the related record instead "
             "(e.g. Customer → VAT).")
    label = fields.Char(help="Leave empty to use the field's own label.")
    align = fields.Selection(
        [('auto', 'Auto'), ('left', 'Left'), ('center', 'Centre'), ('right', 'Right')],
        default='auto')
    width = fields.Integer('Width %', help="0 = automatic.")
    sum_total = fields.Boolean('Total', help="Show the sum of this column in a footer row.")

    # ------------------------------------------------------------------
    def _path(self):
        self.ensure_one()
        path = self.field_id.name
        if self.sub_field_id and self.field_id.ttype == 'many2one':
            path += '.%s' % self.sub_field_id.name
        return path

    def _label(self):
        self.ensure_one()
        if self.label:
            return self.label
        if self.sub_field_id and self.field_id.ttype == 'many2one':
            return self.sub_field_id.field_description or self.sub_field_id.name
        return self.field_id.field_description or self.field_id.name or ''

    def _align(self, orm_field):
        self.ensure_one()
        if self.align and self.align != 'auto':
            return self.align
        return 'right' if orm_field.type in ('integer', 'float', 'monetary') else 'left'

    @api.constrains('field_id', 'sub_field_id', 'block_id')
    def _check_fields(self):
        for item in self:
            expected = item.block_id.source_model
            if expected and item.field_id.model != expected:
                raise ValidationError(_(
                    "Field '%(field)s' belongs to %(model)s, but this block works on %(expected)s.",
                    field=item.field_id.field_description, model=item.field_id.model,
                    expected=expected))
            if item.sub_field_id and item.sub_field_id.model != item.field_id.relation:
                raise ValidationError(_(
                    "Sub-field '%(sub)s' does not belong to the related model of '%(field)s'.",
                    sub=item.sub_field_id.field_description,
                    field=item.field_id.field_description))
