/** @odoo-module **/
import { Component, proxy, useEffect, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class ReportRangeField extends Component {
    static template = "sh_report_builder.RangeField";
    props = useProps(standardFieldProps);
    setup() {
        this.editing = false;
        this.state = proxy({ value: this.props.record.data[this.props.name] || 0 });
        useEffect(() => {
            const value = this.props.record.data[this.props.name] || 0;
            if (!this.editing) this.state.value = value;
        });
    }
    get minimum() { return this.props.name === "background_scale" ? 1 : 0; }
    get maximum() { return this.props.name === "background_saturation" ? 200 : 100; }
    input(event) {
        this.editing = true;
        const value = Number(event.target.value);
        this.state.value = Math.min(this.maximum, Math.max(this.minimum, Number.isFinite(value) ? value : this.minimum));
    }
    commit() {
        this.editing = false;
        if (this.state.value !== this.props.record.data[this.props.name]) {
            return this.props.record.update({ [this.props.name]: this.state.value });
        }
    }
}
registry.category("fields").add("sh_report_builder_range", {
    component: ReportRangeField, supportedTypes: ["integer"],
});
