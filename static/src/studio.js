/** @odoo-module **/
import { Component, onWillStart, onWillUpdateProps, onWillUnmount, useEffect, proxy, useProps } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class ReportStudio extends Component {
    static displayName = "Report Studio";
    static template = "sh_report_builder.Studio";
    props = useProps(standardActionServiceProps);
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = proxy({ screen: "reports", designs: [], lines: [], textures: [], body: "none", opacity: 18, previewHtml: "", previewError: "", previewBusy: false, reports: [], page: "classic", line: "plain", busy: false });
        onWillStart(async () => {
            const data = await this.orm.call("report.builder", "studio_data", []);
            Object.assign(this.state, data);
            this.applyNavigation(this.props.action);
        });
        this.previewRequest = 0;
        this.previewTimer = null;
        this.destroyed = false;
        useEffect(() => {
            const { screen, page, line, body, opacity } = this.state;
            clearTimeout(this.previewTimer);
            const request = ++this.previewRequest;
            if (screen !== "preview") return;
            this.previewTimer = setTimeout(async () => {
                this.state.previewBusy = true;
                this.state.previewError = "";
                try {
                    const html = await this.orm.call("report.builder", "studio_preview", [page, line, body, opacity]);
                    if (!this.destroyed && request === this.previewRequest) this.state.previewHtml = html;
                } catch (error) {
                    if (!this.destroyed && request === this.previewRequest) this.state.previewError = error.data?.message || error.message;
                } finally {
                    if (!this.destroyed && request === this.previewRequest) this.state.previewBusy = false;
                }
            }, 200);
        });
        onWillUnmount(() => { this.destroyed = true; this.previewRequest++; clearTimeout(this.previewTimer); });
        onWillUpdateProps((props) => this.applyNavigation(props.action));
    }
    applyNavigation(action) {
        if (action?.params?.gallery) this.newReport();
        else this.state.screen = "reports";
    }
    newReport() {
        this.state.page = "classic";
        this.state.line = "plain";
        this.state.body = "none";
        this.state.opacity = 18;
        this.state.previewHtml = "";
        this.state.screen = "gallery";
    }
    async showReports() {
        const data = await this.orm.call("report.builder", "studio_data", []);
        this.state.reports = data.reports;
        this.state.screen = "reports";
    }
    get selectedDesign() {
        return this.state.designs.find((design) => design.key === this.state.page);
    }
    get selectedLine() {
        return this.state.lines.find((line) => line.key === this.state.line);
    }
    setOpacity(event) { this.state.opacity = Number(event.target.value); }
    choosePage(key) { this.state.page = key; }
    chooseBody(key) { this.state.body = key; }
    chooseLine(key) { this.state.line = key; }
    async configure(blank = false) {
        if (this.state.busy) return;
        this.state.busy = true;
        try {
            const action = await this.orm.call("report.builder", "action_configure_design", [blank ? "none" : this.state.page, blank ? "legacy" : this.state.line, blank ? "none" : this.state.body, blank ? 18 : this.state.opacity]);
            if (this.destroyed) return;
            await this.action.doAction(action, { onClose: async () => {
                if (this.destroyed) return;
                const data = await this.orm.call("report.builder", "studio_data", []);
                if (!this.destroyed) this.state.reports = data.reports;
            } });
        } finally { if (!this.destroyed) this.state.busy = false; }
    }
    openReport(id) {
        return this.action.doAction({ type: "ir.actions.act_window", name: this.state.reports.find((report) => report.id === id)?.name || "Report design", res_model: "report.builder", res_id: id, views: [[false, "form"]], target: "current" });
    }
    openList() { return this.action.doAction("sh_report_builder.sh_report_builder_action", { stackPosition: "replaceCurrentAction" }); }
}
registry.category("actions").add("sh_report_builder.studio", ReportStudio);
