/** @odoo-module **/
import { Component, onWillUnmount, proxy, useEffect, useProps, signal } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useBus, useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class ReportLivePreviewField extends Component {
    static template = "sh_report_builder.LivePreview";
    props = useProps(standardFieldProps);
    setup() {
        this.orm = useService("orm");
        this.viewer = signal.ref();
        this.state = proxy({ enabled: true, busy: false, viewerUrl: "", paper: null, error: "", status: "Waiting for PDF preview" });
        this.timer = null;
        this.requestId = 0;
        this.destroyed = false;
        this.rendering = false;
        this.pending = false;
        this.pdfUrl = null;
        this.oldUrls = [];
        this.pdfFilename = "Report.pdf";
        useEffect(() => {
            const track = (current) => {
                const data = current.data || {};
                for (const name of Object.keys(data)) {
                    const value = data[name];
                    const type = current.fields?.[name]?.type;
                    if ((type === "one2many" || type === "many2many") && value?.records) {
                        for (const child of value.records) track(child);
                    }
                }
            };
            this.props.record.resId;
            track(this.props.record);
            if (this.state.enabled) this.schedule();
        });
        useBus(this.props.record.model.bus, "FIELD_IS_DIRTY", ({ detail }) => {
            if (detail && this.state.enabled) this.schedule();
        });
        onWillUnmount(() => {
            this.destroyed = true;
            this.requestId++;
            clearTimeout(this.timer);
            for (const url of [...this.oldUrls, this.pdfUrl]) if (url) URL.revokeObjectURL(url);
        });
    }
    async viewerLoaded() {
        const app = this.viewer()?.contentWindow?.PDFViewerApplication;
        if (app) {
            await app.initializedPromise;
            if (this.destroyed) return;
            this.setViewerFilename(app);
            app.eventBus.on("documentloaded", () => { if (!this.destroyed) this.setViewerFilename(app); });
            app.eventBus.on("documentinit", () => { if (!this.destroyed) app.pdfSidebar?.close(); });
        }
        for (const url of this.oldUrls) URL.revokeObjectURL(url);
        this.oldUrls = [];
    }
    setViewerFilename(app) {
        app._contentDispositionFilename = this.pdfFilename;
        app.setTitle(this.pdfFilename);
    }
    schedule() {
        clearTimeout(this.timer);
        this.requestId++;
        this.state.status = "Waiting for your edits to settle…";
        this.timer = setTimeout(() => this.refresh(), 350);
    }
    toggle() {
        this.state.enabled = !this.state.enabled;
        if (!this.state.enabled) {
            clearTimeout(this.timer);
            this.pending = false;
            this.requestId++;
            this.state.status = "Live updates paused";
        }
    }
    async refresh() {
        clearTimeout(this.timer);
        if (this.rendering) {
            this.pending = true;
            this.requestId++;
            return;
        }
        const requestId = ++this.requestId;
        const record = this.props.record;
        if (!record.resId) {
            this.state.error = "Save the report once to use live preview.";
            return;
        }
        this.rendering = true;
        this.state.busy = true;
        this.state.error = "";
        this.state.status = "Rendering PDF with your current settings…";
        try {
            const changes = await record.getChanges();
            if (this.destroyed || requestId !== this.requestId) return;
            const result = await this.orm.call("report.builder", "preview_unsaved", [[record.resId], changes], { context: record.context });
            if (this.destroyed || requestId !== this.requestId) return;
            if (result.pdf) {
                this.pdfFilename = result.filename || "Report.pdf";
                const binary = atob(result.pdf);
                const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
                const viewerApp = this.viewer()?.contentWindow?.PDFViewerApplication;
                if (viewerApp && this.state.viewerUrl) {
                    await viewerApp.initializedPromise;
                    if (this.destroyed || requestId !== this.requestId) return;
                    const ready = new Promise((resolve) => {
                        const done = () => { clearTimeout(timeout); viewerApp.eventBus.off("documentinit", done); resolve(); };
                        const timeout = setTimeout(done, 5000);
                        viewerApp.eventBus.on("documentinit", done);
                    });
                    await viewerApp.open({ data: bytes });
                    await ready;
                    if (this.destroyed || requestId !== this.requestId) return;
                    viewerApp.pdfSidebar?.close();
                    this.setViewerFilename(viewerApp);
                } else {
                    const url = URL.createObjectURL(new Blob([bytes], { type: "application/pdf" }));
                    if (this.pdfUrl) this.oldUrls.push(this.pdfUrl);
                    this.pdfUrl = url;
                    this.state.viewerUrl = `/web/static/lib/pdfjs/web/viewer.html?file=${encodeURIComponent(url)}#zoom=page-width&pagemode=none`;
                }
                this.state.paper = result.paper || null;
            }
            this.state.error = result.error || "";
            this.state.status = result.error ? "Draft needs attention" : "PDF preview updated · edits remain unsaved";
        } catch (error) {
            if (!this.destroyed && requestId === this.requestId) {
                this.state.error = error.data?.message || error.message || "PDF preview is temporarily unavailable.";
                this.state.status = "PDF preview unavailable";
            }
        } finally {
            this.rendering = false;
            if (!this.destroyed) {
                this.state.busy = false;
                if (this.pending) {
                    this.pending = false;
                    clearTimeout(this.timer);
                    this.timer = setTimeout(() => this.refresh(), 150);
                }
            }
        }
    }
}
registry.category("fields").add("sh_report_builder_live_preview", {
    component: ReportLivePreviewField, supportedTypes: ["text"],
});
