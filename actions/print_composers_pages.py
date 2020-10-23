"""
This file is part of Giswater 3
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""
# -*- coding: utf-8 -*-
from qgis.core import QgsLayoutExporter, QgsProject
from qgis.PyQt.QtGui import QStandardItem, QStandardItemModel
from qgis.PyQt.QtWidgets import QAction

import csv
import json
import os
from collections import OrderedDict
from encodings.aliases import aliases
from functools import partial

from .. import utils_giswater
from .api_config import ApiConfig
from .api_manage_composer import ApiManageComposer
from .api_parent import ApiParent
from .check_project_result import CheckProjectResult
from .gw_toolbox import GwToolBox
from .parent import ParentAction
from .manage_visit import ManageVisit
from ..ui_manager import CompPagesUi
import time

class PrintCompoPages(ApiParent):

    def __init__(self, iface, settings, controller, plugin_dir):
        """ Class to control toolbar 'go2epa' """

        ApiParent.__init__(self, iface, settings, controller, plugin_dir)



    def open_composers_dialog(self):
        dlg_comp = CompPagesUi()
        self.load_settings(dlg_comp)
        self.populate_cmb_composers(dlg_comp.cmb_composers)
        last_composer = self.controller.plugin_settings_value('last_composer')
        utils_giswater.set_combo_itemData(dlg_comp.cmb_composers, f'{last_composer}', 0)
        last_path = self.controller.plugin_settings_value('psector_pages_path')
        utils_giswater.setWidgetText(dlg_comp, dlg_comp.txt_path, last_path)
        last_prefix = self.controller.plugin_settings_value('psector_prefix_file')
        utils_giswater.setWidgetText(dlg_comp, dlg_comp.txt_prefix, last_prefix)

        dlg_comp.btn_close.clicked.connect(partial(self.close_dialog, dlg_comp))
        dlg_comp.btn_path.clicked.connect(partial(self.get_folder_dialog, dlg_comp, dlg_comp.txt_path))
        dlg_comp.btn_accept.clicked.connect(partial(self.generate_pdfs, dlg_comp))

        self.open_dialog(dlg_comp, dlg_name='dlg_comp_x_pages')


    def populate_cmb_composers(self, combo):
        """
        :param combo: QComboBox to populate with composers
        :return:
        """

        index = 0
        records = []
        layout_manager = QgsProject.instance().layoutManager()
        layouts = layout_manager.layouts()  # QgsPrintLayout
        for layout in layouts:
            elem = [index, layout.name()]
            records.append(elem)
            index = index + 1
        utils_giswater.set_item_data(combo, records, 1)


    def generate_pdfs(self, dialog):
        folder_path = self.manage_folder_path(dialog)
        last_composer = utils_giswater.get_item_data(dialog, dialog.cmb_composers, 0)
        self.controller.plugin_settings_set_value("last_composer", last_composer)
        prefix = utils_giswater.getWidgetText(dialog, dialog.txt_prefix, False, False)
        self.controller.plugin_settings_set_value("psector_prefix_file", prefix)
        self.generate_composer_pages(dialog, folder_path)



    def manage_folder_path(self, dialog):

        folder_path = utils_giswater.getWidgetText(dialog, dialog.txt_path)
        if folder_path is None or folder_path == 'null' or not os.path.exists(folder_path):
            self.get_folder_dialog(dialog, dialog.txt_path)
            folder_path = utils_giswater.getWidgetText(dialog, dialog.txt_path)

        self.controller.plugin_settings_set_value("psector_pages_path", folder_path)
        return folder_path


    def generate_composer_pages(self, dialog, path):

        # Get user current selectors
        form = f'"currentTab":"tab_psector"'
        extras = f'"selectorType":"selector_basic", "filterText":""'
        body = self.create_body(form=form, extras=extras)
        current_selectors = self.controller.get_json('gw_fct_getselectors', body, log_sql=True)

        # Remove all psectors from selectors
        extras = f'"selectorType":"selector_basic", "tabName":"tab_psector", "checkAll":"False", "addSchema":"NULL"'
        body = self.create_body(extras=extras)
        result = self.controller.get_json("gw_fct_setselectors", body, commit=True)

        # Get layout manager object
        layout_manager = QgsProject.instance().layoutManager()

        # Get our layout
        layout_name = utils_giswater.getWidgetText(dialog, dialog.cmb_composers)
        layout = layout_manager.layoutByName(layout_name)

        # Open Composer
        designer = self.iface.openLayoutDesigner(layout)
        layout_view = designer.view()
        designer_window = layout_view.window()
        action = designer_window.findChild(QAction, 'mActionAtlasPreview')
        action.trigger()

        prefix = utils_giswater.getWidgetText(dialog, dialog.txt_prefix, False, False)
        if prefix not in (None, ''):
            prefix += " "

        for formtabs in result['body']['form']['formTabs']:
            if formtabs['tableName'] != 'selector_psector': continue
            if layout.atlas().count() != len(formtabs['fields']):
                msg = "The number of pages in your composition does not match the number of psectors"
                self.controller.show_warning(msg)
                break

            for field in formtabs['fields']:
                name = field['label']
                _id = field['psector_id']
                extras = f'"selectorType":"selector_basic", "tabName":"tab_psector", "id":{_id}, "value":true, '
                extras += f'"isAlone":true, "addSchema":"NULL"'
                body = self.create_body(extras=extras)
                result = self.controller.get_json("gw_fct_setselectors", body, commit=True)
                self.export_to_pdf(layout, path + f"\\{prefix}{name}.pdf")
                action = designer_window.findChild(QAction, 'mActionAtlasNext')
                action.trigger()
        designer_window.close()

        # Restore user selectors
        qgis_project_add_schema = self.controller.plugin_settings_value('gwAddSchema')
        for form_tab in current_selectors['body']['form']['formTabs']:
            if form_tab['tableName'] != "selector_psector":
                continue
            for field in form_tab['fields']:
                _id = field['psector_id']
                extras = (f'"selectorType":"selector_basic", "tabName":"tab_psector", '
                          f'"id":"{_id}", "isAlone":"False", "value":"{field["value"]}", '
                          f'"addSchema":"{qgis_project_add_schema}"')
                body = self.create_body(extras=extras)
                self.controller.get_json('gw_fct_setselectors', body, log_sql=True)


    def export_to_pdf(self, layout, path):
        # Export to PDF file
        if layout:
            try:
                exporter = QgsLayoutExporter(layout)
                exporter.exportToPdf(path, QgsLayoutExporter.PdfExportSettings())
                if os.path.exists(path):
                    message = "Document PDF created in"
                    self.controller.show_info(message, parameter=path)
                    os.startfile(path)
                else:
                    message = "Cannot create file, check if its open"
                    self.controller.show_warning(message, parameter=path)
            except Exception as e:
                self.controller.log_warning(str(e))
                msg = "Cannot create file, check if selected composer is the correct composer"
                self.controller.show_warning(msg, parameter=path)

