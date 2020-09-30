"""
This file is part of Giswater 3
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""
# -*- coding: utf-8 -*-
from qgis.PyQt.QtWidgets import QAbstractItemView, QTableView

from functools import partial

from lib import tools_qt
from core.utils.tools_giswater import load_settings, open_dialog, close_dialog, tab_feature_changed
from core.ui.ui_manager import DocUi, DocManager
import global_vars


from lib.tools_qgis import remove_selection, selection_init, insert_feature
from lib.tools_qt import populate_combo_with_query, delete_records, manage_close, fill_table_object, filter_by_id, \
    delete_selected_object, set_selectionbehavior, set_model_to_table, set_icon, exist_object, set_completer_object, \
    set_completer_widget, set_table_columns

class GwDocument:

    def __init__(self, single_tool=True):
        """ Class to control action 'Add document' of toolbar 'edit' """

        # parameter to set if the document manager is working as
        # single tool or integrated in another tool
        self.single_tool_mode = single_tool
        self.previous_dialog = None
        self.iface = global_vars.iface
        self.controller = global_vars.controller
        self.schema_name = global_vars.schema_name


    def edit_add_file(self):
        self.manage_document()


    def manage_document(self, tablename=None, qtable=None, item_id=None, feature=None, geom_type=None, row=None):
        """ Button 34: Add document """

        # Create the dialog and signals
        self.dlg_add_doc = DocUi()
        load_settings(self.dlg_add_doc)
        self.doc_id = None

        # Capture the current layer to return it at the end of the operation
        cur_active_layer = self.iface.activeLayer()

        set_selectionbehavior(self.dlg_add_doc)

        # Get layers of every geom_type

        # Setting lists
        self.ids = []
        self.list_ids = {}
        self.list_ids['arc'] = []
        self.list_ids['node'] = []
        self.list_ids['connec'] = []
        self.list_ids['gully'] = []
        self.list_ids['element'] = []

        # Setting layers
        self.layers = {}
        self.layers['arc'] = []
        self.layers['node'] = []
        self.layers['connec'] = []
        self.layers['gully'] = []
        self.layers['element'] = []

        self.layers['arc'] = self.controller.get_group_layers('arc')
        self.layers['node'] = self.controller.get_group_layers('node')
        self.layers['connec'] = self.controller.get_group_layers('connec')
        self.layers['element'] = self.controller.get_group_layers('element')

        # Remove 'gully' for 'WS'
        self.project_type = self.controller.get_project_type()
        if self.project_type == 'ws':
            self.dlg_add_doc.tab_feature.removeTab(3)
        else:
            self.layers['gully'] = self.controller.get_group_layers('gully')

        # Remove all previous selections
        if self.single_tool_mode:
            self.layers = remove_selection(True, layers=self.layers)
        if feature is not None:
            layer = self.iface.activeLayer()
            layer.selectByIds([feature.id()])

        # Set icons
        set_icon(self.dlg_add_doc.btn_insert, "111")
        set_icon(self.dlg_add_doc.btn_delete, "112")
        set_icon(self.dlg_add_doc.btn_snapping, "137")

        # Fill combo boxes
        populate_combo_with_query(self.dlg_add_doc, "doc_type", "doc_type")

        # Set current/selected date and link
        if row:
            tools_qt.setCalendarDate(self.dlg_add_doc, 'date', row.value('date'))
            tools_qt.setWidgetText(self.dlg_add_doc, 'path', row.value('path'))
        else:
            tools_qt.setCalendarDate(self.dlg_add_doc, 'date', None)

        # Adding auto-completion to a QLineEdit
        table_object = "doc"
        set_completer_object(self.dlg_add_doc, table_object)

        # Adding auto-completion to a QLineEdit for default feature
        if geom_type is None:
            geom_type = "arc"
        viewname = f"v_edit_{geom_type}"
        set_completer_widget(viewname, self.dlg_add_doc.feature_id, concat(str(geom_type), "_id"))

        # Set signals
        self.dlg_add_doc.btn_path_url.clicked.connect(partial(self.open_web_browser, self.dlg_add_doc, "path"))
        self.dlg_add_doc.btn_path_doc.clicked.connect(partial(self.get_file_dialog, self.dlg_add_doc, "path"))
        self.dlg_add_doc.btn_accept.clicked.connect(
            partial(self.manage_document_accept, table_object, tablename, qtable, item_id))
        # TODO: Set variable  self.layers using return parameters
        self.dlg_add_doc.btn_cancel.clicked.connect(
            partial(manage_close, self.dlg_add_doc, table_object, cur_active_layer, excluded_layers=["v_edit_element"],
                    single_tool_mode=self.single_tool_mode, layers=self.layers))
        # TODO: Set variable  self.layers using return parameters
        self.dlg_add_doc.rejected.connect(
            partial(manage_close, self.dlg_add_doc, table_object, cur_active_layer, excluded_layers=["v_edit_element"],
                    single_tool_mode=self.single_tool_mode, layers=self.layers))
        self.dlg_add_doc.tab_feature.currentChanged.connect(
            partial(tab_feature_changed, self.dlg_add_doc, table_object, excluded_layers=["v_edit_element"]))

        # TODO: Set variables self.ids, self.layers, self.list_ids using return parameters
        self.dlg_add_doc.doc_id.textChanged.connect(partial(exist_object, self.dlg_add_doc, table_object,
                                                            self.single_tool_mode, layers=self.layers, ids=self.ids,
                                                            list_ids=self.list_ids))
        # TODO: Set variables self.ids, self.layers, self.list_ids using return parameters
        self.dlg_add_doc.btn_insert.clicked.connect(partial(insert_feature, self.dlg_add_doc, table_object,
                                                            geom_type=geom_type, ids=self.ids, layers=self.layers,
                                                            list_ids=self.list_ids))
        # TODO: Set variables self.ids, self.layers, self.list_ids using return parameters
        self.dlg_add_doc.btn_delete.clicked.connect(partial(delete_records, self.dlg_add_doc, table_object,
                                                            geom_type=geom_type, layers=self.layers, ids=self.ids,
                                                            list_ids=self.list_ids))
        # TODO: Set variables self.ids, self.layers, self.list_ids using return parameters
        self.dlg_add_doc.btn_snapping.clicked.connect(partial(selection_init, self.dlg_add_doc, table_object,
                                                              geom_type=geom_type, layers=self.layers))
        if feature:
            self.dlg_add_doc.tabWidget.currentChanged.connect(
                partial(self.fill_table_doc, self.dlg_add_doc, geom_type, feature[geom_type + "_id"]))

        # Set default tab 'arc'
        self.dlg_add_doc.tab_feature.setCurrentIndex(0)
        self.geom_type = "arc"
        tab_feature_changed(self.dlg_add_doc, table_object, excluded_layers=["v_edit_element"])

        # Open the dialog
        open_dialog(self.dlg_add_doc, dlg_name='doc', maximize_button=False)

        return self.dlg_add_doc


    def fill_table_doc(self, dialog, geom_type, feature_id):

        widget = "tbl_doc_x_" + geom_type
        widget = dialog.findChild(QTableView, widget)
        widget.setSelectionBehavior(QAbstractItemView.SelectRows)
        expr_filter = f"{geom_type}_id = '{feature_id}'"

        # Set model of selected widget
        table_name = f"{self.schema_name}.v_edit_{geom_type}"
        set_model_to_table(widget, table_name, expr_filter)


    def manage_document_accept(self, table_object, tablename=None, qtable=None, item_id=None):
        """ Insert or update table 'document'. Add document to selected feature """

        # Get values from dialog
        doc_id = tools_qt.getWidgetText(self.dlg_add_doc, "doc_id")
        doc_type = tools_qt.getWidgetText(self.dlg_add_doc, "doc_type", return_string_null=True)
        date = tools_qt.getCalendarDate(self.dlg_add_doc, "date", datetime_format="yyyy/MM/dd")
        observ = tools_qt.getWidgetText(self.dlg_add_doc, "observ", return_string_null=False)
        path = tools_qt.getWidgetText(self.dlg_add_doc, "path", return_string_null=False)

        if doc_type == 'null':
            message = "You need to insert doc_type"
            self.controller.show_warning(message)
            return

        # Check if this document already exists
        sql = (f"SELECT DISTINCT(id)"
               f" FROM {table_object}"
               f" WHERE id = '{doc_id}'")
        row = self.controller.get_row(sql, log_info=False)

        # If document not exists perform an INSERT
        if row is None:
            if doc_id == 'null':
                sql = (f"INSERT INTO doc (doc_type, path, observ, date)"
                       f" VALUES ('{doc_type}', '{path}', '{observ}', '{date}') RETURNING id;")
                new_doc_id = self.controller.execute_returning(sql)
                sql = ""
                doc_id = str(new_doc_id[0])
            else:
                sql = (f"INSERT INTO doc (id, doc_type, path, observ, date)"
                       f" VALUES ('{doc_id}', '{doc_type}', '{path}', '{observ}', '{date}');")

        # If document exists perform an UPDATE
        else:
            message = "Are you sure you want to update the data?"
            answer = self.controller.ask_question(message)
            if not answer:
                return
            sql = (f"UPDATE doc "
                   f" SET doc_type = '{doc_type}', observ = '{observ}', path = '{path}', date = '{date}'"
                   f" WHERE id = '{doc_id}';")

        # Manage records in tables @table_object_x_@geom_type
        sql += (f"\nDELETE FROM doc_x_node"
                f" WHERE doc_id = '{doc_id}';")
        sql += (f"\nDELETE FROM doc_x_arc"
                f" WHERE doc_id = '{doc_id}';")
        sql += (f"\nDELETE FROM doc_x_connec"
                f" WHERE doc_id = '{doc_id}';")
        if self.project_type == 'ud':
            sql += (f"\nDELETE FROM doc_x_gully"
                    f" WHERE doc_id = '{doc_id}';")

        if self.list_ids['arc']:
            for feature_id in self.list_ids['arc']:
                sql += (f"\nINSERT INTO doc_x_arc (doc_id, arc_id)"
                        f" VALUES ('{doc_id}', '{feature_id}');")
        if self.list_ids['node']:
            for feature_id in self.list_ids['node']:
                sql += (f"\nINSERT INTO doc_x_node (doc_id, node_id)"
                        f" VALUES ('{doc_id}', '{feature_id}');")
        if self.list_ids['connec']:
            for feature_id in self.list_ids['connec']:
                sql += (f"\nINSERT INTO doc_x_connec (doc_id, connec_id)"
                        f" VALUES ('{doc_id}', '{feature_id}');")
        if self.project_type == 'ud' and self.list_ids['gully']:
            for feature_id in self.list_ids['gully']:
                sql += (f"\nINSERT INTO doc_x_gully (doc_id, gully_id)"
                        f" VALUES ('{doc_id}', '{feature_id}');")

        status = self.controller.execute_sql(sql)
        if status:
            self.doc_id = doc_id
            manage_close(self.dlg_add_doc, table_object, excluded_layers=["v_edit_element"],
                         single_tool_mode=self.single_tool_mode, layers=self.layers)

        if tablename is None:
            return
        else:
            sql = (f"INSERT INTO doc_x_{tablename} (doc_id, {tablename}_id) "
                   f" VALUES('{doc_id}', '{item_id}')")
            self.controller.execute_sql(sql)
            expr = f"{tablename}_id = '{item_id}'"
            fill_table_object(qtable, f"{self.schema_name}.v_ui_doc_x_{tablename}", expr_filter=expr)


    def edit_document(self):
        """ Button 66: Edit document """

        # Create the dialog
        self.dlg_man = DocManager()
        load_settings(self.dlg_man)
        self.dlg_man.tbl_document.setSelectionBehavior(QAbstractItemView.SelectRows)

        # Adding auto-completion to a QLineEdit
        table_object = "doc"
        set_completer_object(self.dlg_man, table_object)

        # Set a model with selected filter. Attach that model to selected table
        fill_table_object(self.dlg_man.tbl_document, self.schema_name + "." + table_object)
        set_table_columns(self.dlg_man, self.dlg_man.tbl_document, table_object)

        # Set dignals
        self.dlg_man.doc_id.textChanged.connect(
            partial(filter_by_id, self.dlg_man, self.dlg_man.tbl_document, self.dlg_man.doc_id, table_object))
        self.dlg_man.tbl_document.doubleClicked.connect(
            partial(self.open_selected_object_document, self.dlg_man, self.dlg_man.tbl_document, table_object))
        self.dlg_man.btn_cancel.clicked.connect(partial(close_dialog, self.dlg_man))
        self.dlg_man.rejected.connect(partial(close_dialog, self.dlg_man))
        self.dlg_man.btn_delete.clicked.connect(
            partial(delete_selected_object, self.dlg_man.tbl_document, table_object))

        # Open form
        open_dialog(self.dlg_man, dlg_name='doc_manager')


    def open_selected_object_document(self, dialog, widget, table_object):

        selected_list = widget.selectionModel().selectedRows()
        if len(selected_list) == 0:
            message = "Any record selected"
            self.controller.show_warning(message)
            return

        row = selected_list[0].row()

        # Get object_id from selected row
        field_object_id = "id"
        widget_id = table_object + "_id"
        selected_object_id = widget.model().record(row).value(field_object_id)

        # Close this dialog and open selected object
        dialog.close()

        self.manage_document(row=widget.model().record(row))
        tools_qt.setWidgetText(self.dlg_add_doc, widget_id, selected_object_id)


    def open_web_browser(self, dialog, widget=None):
        """ Display url using the default browser """

        if widget is not None:
            url = tools_qt.getWidgetText(dialog, widget)
            if url == 'null':
                url = 'http://www.giswater.org'
        else:
            url = 'http://www.giswater.org'

        webbrowser.open(url)


    def get_file_dialog(self, dialog, widget):
        """ Get file dialog """

        # Check if selected file exists. Set default value if necessary
        file_path = tools_qt.getWidgetText(dialog, widget)
        if file_path is None or file_path == 'null' or not os.path.exists(str(file_path)):
            folder_path = global_vars.plugin_dir
        else:
            folder_path = os.path.dirname(file_path)

        # Open dialog to select file
        os.chdir(folder_path)
        file_dialog = QFileDialog()
        file_dialog.setFileMode(QFileDialog.AnyFile)
        message = "Select file"
        folder_path, filter_ = file_dialog.getOpenFileName(parent=None, caption=global_vars.controller.tr(message))
        if folder_path:
            tools_qt.setWidgetText(dialog, widget, str(folder_path))