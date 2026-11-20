/** @odoo-module **/
import "./studio";
import { registry } from "@web/core/registry";
import { formView } from "@web/views/form/form_view";
import { FormController } from "@web/views/form/form_controller";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";

function studioAction(gallery) {
    return {
        type: "ir.actions.client", tag: "sh_report_builder.studio",
        name: "Report Studio", display_name: "Report Studio",
        params: gallery ? { gallery: true } : { screen: "reports" },
    };
}
export class ReportBuilderFormController extends FormController {
    static template = "sh_report_builder.FormView";
    create() { return this.actionService.doAction(studioAction(true)); }
    openReportStudio() { return this.actionService.doAction(studioAction(false)); }
    openReportList() { return this.actionService.doAction("sh_report_builder.sh_report_builder_action"); }
}
export class ReportBuilderListController extends ListController {
    static template = "sh_report_builder.ListView";
    createRecord() { return this.actionService.doAction(studioAction(true)); }
    openReportStudio() {
        return this.actionService.doAction(studioAction(false), { stackPosition: "replaceCurrentAction" });
    }
}
registry.category("views").add("sh_report_builder_form", {
    ...formView, Controller: ReportBuilderFormController,
    buttonTemplate: "sh_report_builder.FormNavigation",
});
registry.category("views").add("sh_report_builder_list", {
    ...listView, Controller: ReportBuilderListController,
    buttonTemplate: "sh_report_builder.ListNavigation",
});
