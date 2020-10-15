"""
This file is part of Giswater 3
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""
# -*- coding: latin-1 -*-
import os
import json

from qgis.core import QgsCategorizedSymbolRenderer, QgsDataSourceUri, QgsFeature, QgsField, QgsGeometry, QgsFillSymbol,\
    QgsMarkerSymbol, QgsLayerTreeLayer, QgsLineSymbol, QgsProject, QgsRectangle, QgsRendererCategory, \
    QgsSymbol, QgsVectorLayer, QgsVectorLayerExporter
from qgis.gui import QgsDateTimeEdit
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtGui import QColor, QIcon, QStandardItemModel, QStandardItem
from qgis.PyQt.QtWidgets import QSpinBox, QDoubleSpinBox, QTextEdit, QWidget, QLabel, QLineEdit, QComboBox, QCheckBox, \
    QGridLayout, QRadioButton, QAbstractItemView, QPushButton, QTabWidget
from collections import OrderedDict
from functools import partial

from ...lib import tools_qt
from ..utils.tools_giswater import getWidgetText, open_file_path, set_style_mapzones
from ..shared.api_parent import ApiParent
from ..ui.ui_manager import ToolboxDockerUi, ToolboxUi

from random import randrange
from ... import global_vars


class GwToolBox(ApiParent):

    def __init__(self, iface, settings, controller, plugin_dir):
        """ Class to control toolbar 'om_ws' """

        ApiParent.__init__(self, iface, settings, controller, plugin_dir)
        self.function_list = []
        self.rbt_checked = {}
        self.is_paramtetric = True
        self.no_clickable_items = ['Giswater']


    def set_project_type(self, project_type):
        self.project_type = project_type


    def open_toolbox(self):

        function_name = "gw_fct_gettoolbox"
        row = self.controller.check_function(function_name)
        if not row:
            self.controller.show_warning("Function not found in database", parameter=function_name)
            return

        self.dlg_toolbox_doc = ToolboxDockerUi()
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dlg_toolbox_doc)
        self.dlg_toolbox_doc.trv.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.dlg_toolbox_doc.trv.setHeaderHidden(True)
        extras = '"isToolbox":true'
        body = self.create_body(extras=extras)
        json_result = self.controller.get_json('gw_fct_gettoolbox', body)
        if not json_result or json_result['status'] == 'Failed':
            return False

        self.populate_trv(self.dlg_toolbox_doc.trv, json_result['body']['data'])
        self.dlg_toolbox_doc.txt_filter.textChanged.connect(partial(self.filter_functions))
        self.dlg_toolbox_doc.trv.doubleClicked.connect(partial(self.open_function))
        self.controller.manage_translation('toolbox_docker', self.dlg_toolbox_doc)


    def filter_functions(self, text):

        extras = f'"filterText":"{text}"'
        body = self.create_body(extras=extras)
        json_result = self.controller.get_json('gw_fct_gettoolbox', body)
        if not json_result or json_result['status'] == 'Failed':
            return False

        self.populate_trv(self.dlg_toolbox_doc.trv, json_result['body']['data'], expand=True)


    def open_function(self, index):

        self.is_paramtetric = True
        # this '0' refers to the index of the item in the selected row (alias in this case)
        self.alias_function = index.sibling(index.row(), 0).data()

        # Control no clickable items
        if self.alias_function in self.no_clickable_items:
            return

        self.dlg_functions = ToolboxUi()
        self.load_settings(self.dlg_functions)
        self.dlg_functions.progressBar.setVisible(False)

        self.dlg_functions.cmb_layers.currentIndexChanged.connect(partial(self.set_selected_layer, self.dlg_functions,
                                                                          self.dlg_functions.cmb_layers))
        self.dlg_functions.rbt_previous.toggled.connect(partial(self.rbt_state, self.dlg_functions.rbt_previous))
        self.dlg_functions.rbt_layer.toggled.connect(partial(self.rbt_state, self.dlg_functions.rbt_layer))
        self.dlg_functions.rbt_layer.setChecked(True)

        extras = f'"filterText":"{self.alias_function}"'
        extras += ', "isToolbox":true'
        body = self.create_body(extras=extras)
        json_result = self.controller.get_json('gw_fct_gettoolbox', body)
        if not json_result or json_result['status'] == 'Failed':
            return False

        status = self.populate_functions_dlg(self.dlg_functions, json_result['body']['data'])
        if not status:
            self.alias_function = index.sibling(index.row(), 1).data()
            message = "Function not found"
            self.controller.show_message(message, parameter=self.alias_function)
            return

        self.dlg_functions.btn_run.clicked.connect(partial(self.execute_function, self.dlg_functions,
                                                   self.dlg_functions.cmb_layers, json_result['body']['data']))
        self.dlg_functions.btn_close.clicked.connect(partial(self.close_dialog, self.dlg_functions))
        self.dlg_functions.btn_cancel.clicked.connect(partial(self.remove_layers))
        self.dlg_functions.btn_cancel.clicked.connect(partial(self.close_dialog, self.dlg_functions))
        enable_btn_run = index.sibling(index.row(), 2).data()
        bool_dict = {"True": True, "true": True, "False": False, "false": False}
        self.dlg_functions.btn_run.setEnabled(bool_dict[enable_btn_run])
        self.dlg_functions.btn_cancel.setEnabled(bool_dict[enable_btn_run])
        self.open_dialog(self.dlg_functions, dlg_name='toolbox', title=self.alias_function)


    def remove_layers(self):

        root = QgsProject.instance().layerTreeRoot()
        for layer in reversed(self.temp_layers_added):
            self.temp_layers_added.remove(layer)
            # Possible QGIS bug: Instead of returning None because it is not found in the TOC, it breaks
            try:
                dem_raster = root.findLayer(layer.id())
            except RuntimeError:
                continue

            parent_group = dem_raster.parent()
            try:
                QgsProject.instance().removeMapLayer(layer.id())
            except Exception:
                pass

            if len(parent_group.findLayers()) == 0:
                root.removeChildNode(parent_group)

        self.iface.mapCanvas().refresh()


    def set_selected_layer(self, dialog, combo):

        layer_name = tools_qt.get_item_data(dialog, combo, 1)
        layer = self.controller.get_layer_by_tablename(layer_name)
        if layer is None:
            self.controller.show_warning("Layer not found", parameter=layer_name)
            return None
        self.iface.setActiveLayer(layer)
        return layer


    def rbt_state(self, rbt, state):

        if rbt.objectName() == 'rbt_previous' and state is True:
            self.rbt_checked['widget'] = 'previousSelection'
        elif rbt.objectName() == 'rbt_layer' and state is True:
            self.rbt_checked['widget'] = 'wholeSelection'

        self.rbt_checked['value'] = state


    def load_settings_values(self, dialog, function):
        """ Load QGIS settings related with toolbox options """

        cur_user = self.controller.get_current_user()
        function_name = function[0]['functionname']
        if dialog.cmb_geom_type.property('selectedId') in (None, '', 'NULL'):
            geom_type = self.controller.plugin_settings_value(f"{function_name}_{cur_user}_cmb_geom_type")
        else:
            geom_type = dialog.cmb_geom_type.property('selectedId')
        tools_qt.set_combo_itemData(dialog.cmb_geom_type, geom_type, 0)
        if dialog.cmb_layers.property('selectedId') in (None, '', 'NULL'):
            layer = self.controller.plugin_settings_value(f"{function_name}_{cur_user}_cmb_layers")
        else:
            layer = dialog.cmb_layers.property('selectedId')
        tools_qt.set_combo_itemData(dialog.cmb_layers, layer, 0)
        if self.controller.plugin_settings_value(f"{function_name}_{cur_user}_rbt_previous") == 'true':
            dialog.rbt_previous.setChecked(True)
        else:
            dialog.rbt_layer.setChecked(True)


    def load_parametric_values(self, dialog, function):
        """ Load QGIS settings related with parametric toolbox options """

        cur_user = self.controller.get_current_user()
        function_name = function[0]['functionname']
        layout = dialog.findChild(QWidget, 'grb_parameters')
        widgets = layout.findChildren(QWidget)
        for widget in widgets:
            if type(widget) not in (QCheckBox, QComboBox, QLineEdit):
                continue
            if type(widget) is QCheckBox:
                if self.controller.plugin_settings_value(f"{function_name}_{cur_user}_{widget.objectName()}"):
                    widget.setChecked(True)
                else:
                    widget.setChecked(False)
            elif type(widget) is QComboBox:
                if widget.property('selectedId') in (None, '', 'NULL'):
                    value = self.controller.plugin_settings_value(f"{function_name}_{cur_user}_{widget.objectName()}")
                else:
                    value = widget.property('selectedId')
                tools_qt.set_combo_itemData(widget, value, 0)
            elif type(widget) in (QLineEdit, QSpinBox):
                value = self.controller.plugin_settings_value(f"{function_name}_{cur_user}_{widget.objectName()}")
                tools_qt.setWidgetText(dialog, widget, value)


    def save_settings_values(self, dialog, function):
        """ Save QGIS settings related with toolbox options """

        cur_user = self.controller.get_current_user()
        function_name = function[0]['functionname']
        geom_type = tools_qt.get_item_data(dialog, dialog.cmb_geom_type, 0)
        self.controller.plugin_settings_set_value(f"{function_name}_{cur_user}_cmb_geom_type", geom_type)
        layer = tools_qt.get_item_data(dialog, dialog.cmb_layers, 0)
        self.controller.plugin_settings_set_value(f"{function_name}_{cur_user}_cmb_layers", layer)
        self.controller.plugin_settings_set_value(f"{function_name}_{cur_user}_rbt_previous", dialog.rbt_previous.isChecked())


    def save_parametric_values(self, dialog, function):
        """ Save QGIS settings related with parametric toolbox options """

        cur_user = self.controller.get_current_user()
        function_name = function[0]['functionname']
        layout = dialog.findChild(QWidget, 'grb_parameters')
        widgets = layout.findChildren(QWidget)
        for widget in widgets:
            if type(widget) is QCheckBox:
                self.controller.plugin_settings_set_value(f"{function_name}_{cur_user}_{widget.objectName()}", widget.isChecked())
            elif type(widget) is QComboBox:
                value = tools_qt.get_item_data(dialog, widget, 0)
                self.controller.plugin_settings_set_value(f"{function_name}_{cur_user}_{widget.objectName()}", value)
            elif type(widget) in (QLineEdit, QSpinBox):
                value = tools_qt.getWidgetText(dialog, widget, False, False)
                self.controller.plugin_settings_set_value(f"{function_name}_{cur_user}_{widget.objectName()}", value)


    def execute_function(self, dialog, combo, result):

        dialog.btn_cancel.setEnabled(False)
        dialog.progressBar.setMaximum(0)
        dialog.progressBar.setMinimum(0)
        dialog.progressBar.setVisible(True)
        extras = ''
        feature_field = ''
        # TODO Check if time functions is short or long, activate and set undetermined  if not short

        # Get function name
        function = None
        function_name = None
        for group, function in list(result['fields'].items()):
            if len(function) != 0:
                self.save_settings_values(dialog, function)
                self.save_parametric_values(dialog, function)
                function_name = function[0]['functionname']
                break

        if function_name is None:
            return

        # If function is not parametrized, call function(old) without json
        if self.is_paramtetric is False:
            self.execute_no_parametric(dialog, function_name)
            dialog.progressBar.setVisible(False)
            dialog.progressBar.setMinimum(0)
            dialog.progressBar.setMaximum(1)
            dialog.progressBar.setValue(1)
            return

        if function[0]['input_params']['featureType']:
            layer = None
            layer_name = tools_qt.get_item_data(dialog, combo, 1)
            if layer_name != -1:
                layer = self.set_selected_layer(dialog, combo)
                if not layer:
                    dialog.progressBar.setVisible(False)
                    dialog.progressBar.setMinimum(0)
                    dialog.progressBar.setMaximum(1)
                    dialog.progressBar.setValue(1)
                    return

            selection_mode = self.rbt_checked['widget']
            extras += f'"selectionMode":"{selection_mode}",'
            # Check selection mode and get (or not get) all feature id
            feature_id_list = '"id":['
            if (selection_mode == 'wholeSelection') or (selection_mode == 'previousSelection' and layer is None):
                feature_id_list += ']'
            elif selection_mode == 'previousSelection' and layer is not None:
                features = layer.selectedFeatures()
                feature_type = tools_qt.get_item_data(dialog, dialog.cmb_geom_type, 0)
                for feature in features:
                    feature_id = feature.attribute(feature_type + "_id")
                    feature_id_list += f'"{feature_id}", '
                if len(features) > 0:
                    feature_id_list = feature_id_list[:-2] + ']'
                else:
                    feature_id_list += ']'

            if layer_name != -1:
                feature_field = f'"tableName":"{layer_name}", '
                feature_type = tools_qt.get_item_data(dialog, dialog.cmb_geom_type, 0)
                feature_field += f'"featureType":"{feature_type}", '
            feature_field += feature_id_list

        widget_list = dialog.grb_parameters.findChildren(QWidget)
        widget_is_void = False
        extras += '"parameters":{'
        for group, function in list(result['fields'].items()):
            if len(function) != 0:
                if function[0]['return_type'] not in (None, ''):
                    for field in function[0]['return_type']:
                        widget = dialog.findChild(QWidget, field['widgetname'])
                        param_name = widget.objectName()
                        if type(widget) in ('', QLineEdit):
                            widget.setStyleSheet(None)
                            value = tools_qt.getWidgetText(dialog, widget, False, False)
                            extras += f'"{param_name}":"{value}", '.replace('""', 'null')
                            if value is '' and widget.property('ismandatory'):
                                widget_is_void = True
                                widget.setStyleSheet("border: 1px solid red")
                        elif type(widget) in ('', QSpinBox, QDoubleSpinBox):
                            value = tools_qt.getWidgetText(dialog, widget, False, False)
                            if value == '':
                                value = 0
                            extras += f'"{param_name}":"{value}", '
                        elif type(widget) in ('', QComboBox):
                            value = tools_qt.get_item_data(dialog, widget, 0)
                            extras += f'"{param_name}":"{value}", '
                        elif type(widget) in ('', QCheckBox):
                            value = tools_qt.isChecked(dialog, widget)
                            extras += f'"{param_name}":"{str(value).lower()}", '
                        elif type(widget) in ('', QgsDateTimeEdit):
                            value = tools_qt.getCalendarDate(dialog, widget)
                            if value == "" or value is None:
                                extras += f'"{param_name}":null, '
                            else:
                                extras += f'"{param_name}":"{value}", '

        if widget_is_void:
            message = "This param is mandatory. Please, set a value"
            self.controller.show_warning(message, parameter='')
            dialog.progressBar.setVisible(False)
            dialog.progressBar.setMinimum(0)
            dialog.progressBar.setMaximum(1)
            dialog.progressBar.setValue(1)
            return

        dialog.progressBar.setFormat(f"Running function: {function_name}")
        dialog.progressBar.setAlignment(Qt.AlignCenter)

        if len(widget_list) > 0:
            extras = extras[:-2] + '}'
        else:
            extras += '}'

        body = self.create_body(feature=feature_field, extras=extras)
        json_result = self.controller.get_json(function_name, body, log_sql=True)
        if json_result['status'] == 'Failed': return
        self.populate_info_text(dialog, json_result['body']['data'], True, True, 1, True)

        dialog.progressBar.setAlignment(Qt.AlignCenter)
        dialog.progressBar.setMinimum(0)
        dialog.progressBar.setMaximum(1)
        dialog.progressBar.setValue(1)
        if json_result is None:
            dialog.progressBar.setFormat(f"Function: {function_name} executed with no result")
            return True

        if not json_result:
            dialog.progressBar.setFormat(f"Function: {function_name} failed. See log file for more details")
            return False

        try:
            dialog.progressBar.setFormat(f"Function {function_name} has finished")

            # getting simbology capabilities
            if 'setStyle' in json_result['body']['data']:
                set_sytle = json_result['body']['data']['setStyle']
                if set_sytle == "Mapzones":
                    # call function to simbolize mapzones
                    set_style_mapzones()

        except KeyError as e:
            msg = f"<b>Key: </b>{e}<br>"
            msg += f"<b>key container: </b>'body/data/ <br>"
            msg += f"<b>Python file: </b>{__name__} <br>"
            msg += f"<b>Python function:</b> {self.execute_function.__name__} <br>"
            self.show_exceptions_msg("Key on returned json from ddbb is missed.", msg)

        self.remove_layers()


    def execute_no_parametric(self, dialog, function_name):

        dialog.progressBar.setMinimum(0)
        dialog.progressBar.setFormat(f"Running function: {function_name}")
        dialog.progressBar.setAlignment(Qt.AlignCenter)
        dialog.progressBar.setFormat("")

        sql = f"SELECT {function_name}()::text"
        row = self.controller.get_row(sql)
        if not row or row[0] in (None, ''):
            self.controller.show_message(f"Function: {function_name} executed with no result ", 3)
            return True

        complet_result = [json.loads(row[0], object_pairs_hook=OrderedDict)]
        self.add_temp_layer(dialog, complet_result[0]['body']['data'], self.alias_function)
        dialog.progressBar.setFormat(f"Function {function_name} has finished.")
        dialog.progressBar.setAlignment(Qt.AlignCenter)

        return True


    def populate_functions_dlg(self, dialog, result):

        status = False
        for group, function in result['fields'].items():
            if len(function) != 0:
                dialog.setWindowTitle(function[0]['alias'])
                dialog.txt_info.setText(str(function[0]['descript']))
                if str(function[0]['isparametric']) in ('false', 'False', False, 'None', None, 'null'):
                    self.is_paramtetric = False
                    self.control_isparametric(dialog)
                    self.load_settings_values(dialog, function)
                    if str(function[0]['isnotparammsg']) is not None:
                        layout = dialog.findChild(QGridLayout, 'grl_option_parameters')
                        if layout is None:
                            status = True
                            break
                        label = QLabel()
                        label.setWordWrap(True)
                        label.setText("Info: " + str(function[0]['isnotparammsg']))
                        layout.addWidget(label, 0, 0)
                    status = True
                    break
                if not function[0]['input_params']['featureType']:
                    dialog.grb_input_layer.setVisible(False)
                    dialog.grb_selection_type.setVisible(False)
                else:
                    feature_types = function[0]['input_params']['featureType']
                    self.populate_cmb_type(feature_types)
                    self.dlg_functions.cmb_geom_type.currentIndexChanged.connect(partial(self.populate_layer_combo))
                    self.populate_layer_combo()
                self.construct_form_param_user(dialog, function, 0, self.function_list)
                self.load_settings_values(dialog, function)
                self.load_parametric_values(dialog, function)
                status = True
                break

        return status


    def populate_cmb_type(self, feature_types):

        feat_types = []
        for item in feature_types:
            elem = []
            elem.append(item.upper())
            elem.append(item.upper())
            feat_types.append(elem)
        if feat_types and len(feat_types) <= 1:
            self.dlg_functions.cmb_geom_type.setVisible(False)
        tools_qt.set_item_data(self.dlg_functions.cmb_geom_type, feat_types, 1)


    def get_all_group_layers(self, geom_type):

        list_items = []
        sql = (f"SELECT tablename, type FROM "
               f"(SELECT DISTINCT(parent_layer) AS tablename, feature_type as type, 0 as c "
               f"FROM cat_feature WHERE feature_type = '{geom_type.upper()}' "
               f"UNION SELECT child_layer, feature_type, 2 as c "
               f"FROM cat_feature WHERE feature_type = '{geom_type.upper()}') as t "
               f"ORDER BY c, tablename")
        rows = self.controller.get_rows(sql)
        if rows:
            for row in rows:
                layer = self.controller.get_layer_by_tablename(row[0])
                if layer:
                    elem = [row[1], layer]
                    list_items.append(elem)

        return list_items


    def control_isparametric(self, dialog):
        """ Control if the function is not parameterized whit a json, is old and we need disable all widgets """

        widget_list = dialog.findChildren(QWidget)
        for widget in widget_list:
            if type(widget) in (QDoubleSpinBox, QLineEdit, QSpinBox, QTextEdit):
                widget.setReadOnly(True)
                widget.setStyleSheet("QWidget { background: rgb(242, 242, 242); color: rgb(100, 100, 100)}")
            elif type(widget) in (QCheckBox, QComboBox, QRadioButton):
                widget.setEnabled(False)

        dialog.grb_input_layer.setVisible(False)
        dialog.grb_selection_type.setVisible(False)
        dialog.rbt_previous.setChecked(False)
        dialog.rbt_layer.setChecked(True)

        dialog.grb_parameters.setEnabled(False)
        dialog.grb_parameters.setStyleSheet("QWidget { background: rgb(242, 242, 242); color: rgb(100, 100, 100)}")

        dialog.txt_info.setReadOnly(True)
        dialog.txt_info.setStyleSheet("QWidget { background: rgb(255, 255, 255); color: rgb(10, 10, 10)}")


    def populate_layer_combo(self):

        geom_type = tools_qt.get_item_data(self.dlg_functions, self.dlg_functions.cmb_geom_type, 0)
        self.layers = []
        self.layers = self.get_all_group_layers(geom_type)

        layers = []
        legend_layers = self.controller.get_layers()
        for geom_type, layer in self.layers:
            if layer in legend_layers:
                elem = []
                layer_name = self.controller.get_layer_source_table_name(layer)
                elem.append(layer.name())
                elem.append(layer_name)
                elem.append(geom_type)
                layers.append(elem)
        if not layers:
            elem = []
            elem.append(f"There is no layer related to {geom_type}.")
            elem.append(None)
            elem.append(None)
            layers.append(elem)

        tools_qt.set_item_data(self.dlg_functions.cmb_layers, layers, sort_combo=False)


    def populate_trv(self, trv_widget, result, expand=False):

        model = QStandardItemModel()
        trv_widget.setModel(model)
        trv_widget.setUniformRowHeights(False)
        main_parent = QStandardItem('{}'.format('Giswater'))
        font = main_parent.font()
        font.setPointSize(8)
        main_parent.setFont(font)

        self.icon_folder = self.plugin_dir + os.sep + 'icons'
        path_icon_blue = self.icon_folder + os.sep + '36.png'
        path_icon_red = self.icon_folder + os.sep + '100.png'
        if os.path.exists(path_icon_blue):
            icon = QIcon(path_icon_blue)
            main_parent.setIcon(icon)

        for group, functions in result['fields'].items():
            parent1 = QStandardItem(f'{group}   [{len(functions)} Giswater algorithm]')
            self.no_clickable_items.append(f'{group}   [{len(functions)} Giswater algorithm]')
            functions.sort(key=self.sort_list, reverse=False)
            for function in functions:
                func_name = QStandardItem(str(function['functionname']))
                label = QStandardItem(str(function['alias']))
                font = label.font()
                font.setPointSize(8)
                label.setFont(font)
                row = self.controller.check_function(function['functionname'])
                if not row:
                    if os.path.exists(path_icon_red):
                        icon = QIcon(path_icon_red)
                        label.setIcon(icon)
                        label.setForeground(QColor(255, 0, 0))
                        msg = f"Function {function['functionname']}" \
                            f" configured on the table config_toolbox, but not found in the database"
                        label.setToolTip(msg)
                        self.no_clickable_items.append(str(function['alias']))
                else:
                    if os.path.exists(path_icon_blue):
                        icon = QIcon(path_icon_blue)
                        label.setIcon(icon)
                        label.setToolTip(function['functionname'])
                enable_run = QStandardItem("True")
                if function['input_params'] is not None:
                    if 'btnRunEnabled' in function['input_params']:
                        bool_dict = {True: "True", False: "False"}
                        enable_run = QStandardItem(bool_dict[function['input_params']['btnRunEnabled']])

                parent1.appendRow([label, func_name, enable_run])
            main_parent.appendRow(parent1)
        model.appendRow(main_parent)
        index = model.indexFromItem(main_parent)
        trv_widget.expand(index)
        if expand:
            trv_widget.expandAll()


    def sort_list(self, json):

        try:
            return json['alias'].upper()
        except KeyError:
            return 0


    def gw_function_dxf(self, **kwargs):
        """ Function called in def add_button(self, dialog, field): -->
                widget.clicked.connect(partial(getattr(self, function_name), dialog, widget)) """

        path, filter_ = open_file_path(filter_="DXF Files (*.dxf)")
        if not path:
            return

        dialog = kwargs['dialog']
        widget = kwargs['widget']
        temp_layers_added = kwargs['temp_layers_added']
        complet_result = self.manage_dxf(dialog, path, False, True)

        for layer in complet_result['temp_layers_added']:
            temp_layers_added.append(layer)
        if complet_result is not False:
            widget.setText(complet_result['path'])

        dialog.btn_run.setEnabled(True)
        dialog.btn_cancel.setEnabled(True)


    def manage_dxf(self, dialog, dxf_path, export_to_db=False, toc=False, del_old_layers=True):
        """ Select a dxf file and add layers into toc
        :param dxf_path: path of dxf file
        :param export_to_db: Export layers to database
        :param toc: insert layers into TOC
        :param del_old_layers: look for a layer with the same name as the one to be inserted and delete it
        :return:
        """

        srid = self.controller.plugin_settings_value('srid')
        # Block the signals so that the window does not appear asking for crs / srid and / or alert message
        self.iface.mainWindow().blockSignals(True)
        dialog.txt_infolog.clear()

        sql = "DELETE FROM temp_table WHERE fid = 206;\n"
        self.controller.execute_sql(sql)
        temp_layers_added = []
        for type_ in ['LineString', 'Point', 'Polygon']:

            # Get file name without extension
            dxf_output_filename = os.path.splitext(os.path.basename(dxf_path))[0]

            # Create layer
            uri = f"{dxf_path}|layername=entities|geometrytype={type_}"
            dxf_layer = QgsVectorLayer(uri, f"{dxf_output_filename}_{type_}", 'ogr')

            # Set crs to layer
            crs = dxf_layer.crs()
            crs.createFromId(srid)
            dxf_layer.setCrs(crs)

            if not dxf_layer.hasFeatures():
                continue

            # Get the name of the columns
            field_names = [field.name() for field in dxf_layer.fields()]

            sql = ""
            geom_types = {0: 'geom_point', 1: 'geom_line', 2: 'geom_polygon'}
            for count, feature in enumerate(dxf_layer.getFeatures()):
                geom_type = feature.geometry().type()
                sql += (f"INSERT INTO temp_table (fid, text_column, {geom_types[int(geom_type)]})"
                        f" VALUES (206, '{{")
                for att in field_names:
                    if feature[att] in (None, 'NULL', ''):
                        sql += f'"{att}":null , '
                    else:
                        sql += f'"{att}":"{feature[att]}" , '
                geometry = self.manage_geometry(feature.geometry())
                sql = sql[:-2] + f"}}', (SELECT ST_GeomFromText('{geometry}', {srid})));\n"
                if count != 0 and count % 500 == 0:
                    status = self.controller.execute_sql(sql)
                    if not status:
                        return False
                    sql = ""

            if sql != "":
                status = self.controller.execute_sql(sql)
                if not status:
                    return False

            if export_to_db:
                self.export_layer_to_db(dxf_layer, crs)

            if del_old_layers:
                self.delete_layer_from_toc(dxf_layer.name())

            if toc:
                if dxf_layer.isValid():
                    self.from_dxf_to_toc(dxf_layer, dxf_output_filename)
                    temp_layers_added.append(dxf_layer)

        # Unlock signals
        self.iface.mainWindow().blockSignals(False)

        extras = "  "
        for widget in dialog.grb_parameters.findChildren(QWidget):
            widget_name = widget.property('columnname')
            value = getWidgetText(dialog, widget, add_quote=False)
            extras += f'"{widget_name}":"{value}", '
        extras = extras[:-2]
        body = self.create_body(extras)
        result = self.controller.get_json('gw_fct_check_importdxf', None)
        if not result or result['status'] == 'Failed':
            return False

        return {"path": dxf_path, "result": result, "temp_layers_added": temp_layers_added}


    def set_uri(self):
        """ Set the component parts of a RDBMS data source URI
        :return: QgsDataSourceUri() with the connection established according to the parameters of the controller.
        """

        self.uri = QgsDataSourceUri()
        self.uri.setConnection(self.controller.credentials['host'], self.controller.credentials['port'],
                               self.controller.credentials['db'], self.controller.credentials['user'],
                               self.controller.credentials['password'])
        return self.uri


    def manage_geometry(self, geometry):
        """ Get QgsGeometry and return as text
         :param geometry: (QgsGeometry)
         :return: (String)
        """
        geometry = geometry.asWkt().replace('Z (', ' (')
        geometry = geometry.replace(' 0)', ')')
        return geometry


    def from_dxf_to_toc(self, dxf_layer, dxf_output_filename):
        """  Read a dxf file and put result into TOC
        :param dxf_layer: (QgsVectorLayer)
        :param dxf_output_filename: Name of layer into TOC (string)
        :return: dxf_layer (QgsVectorLayer)
        """

        QgsProject.instance().addMapLayer(dxf_layer, False)
        root = QgsProject.instance().layerTreeRoot()
        my_group = root.findGroup(dxf_output_filename)
        if my_group is None:
            my_group = root.insertGroup(0, dxf_output_filename)
        my_group.insertLayer(0, dxf_layer)
        global_vars.canvas.refreshAllLayers()
        return dxf_layer


    def export_layer_to_db(self, layer, crs):
        """ Export layer to postgres database
        :param layer: (QgsVectorLayer)
        :param crs: QgsVectorLayer.crs() (crs)
        """

        sql = f'DROP TABLE "{layer.name()}";'
        self.controller.execute_sql(sql)

        schema_name = self.controller.credentials['schema'].replace('"', '')
        self.set_uri()
        self.uri.setDataSource(schema_name, layer.name(), None, "", layer.name())

        error = QgsVectorLayerExporter.exportLayer(
            layer, self.uri.uri(), self.controller.credentials['user'], crs, False)
        if error[0] != 0:
            self.controller.log_info(F"ERROR --> {error[1]}")


    def from_postgres_to_toc(self, tablename=None, the_geom="the_geom", field_id="id", child_layers=None,
        group="GW Layers", style_id="-1"):
        """ Put selected layer into TOC
        :param tablename: Postgres table name (String)
        :param the_geom: Geometry field of the table (String)
        :param field_id: Field id of the table (String)
        :param child_layers: List of layers (StringList)
        :param group: Name of the group that will be created in the toc (String)
        :param style_id: Id of the style we want to load (integer or String)
        """

        self.set_uri()
        schema_name = self.controller.credentials['schema'].replace('"', '')
        if child_layers is not None:
            for layer in child_layers:
                if layer[0] != 'Load all':
                    self.uri.setDataSource(schema_name, f'{layer[0]}', the_geom, None, layer[1] + "_id")
                    vlayer = QgsVectorLayer(self.uri.uri(), f'{layer[0]}', "postgres")
                    group = layer[4] if layer[4] is not None else group
                    group = group if group is not None else 'GW Layers'
                    self.check_for_group(vlayer, group)
                    style_id = layer[3]
                    if style_id is not None:
                        body = f'$${{"data":{{"style_id":"{style_id}"}}}}$$'
                        style = self.controller.get_json('gw_fct_getstyle', body)
                        if style['status'] == 'Failed': return
                        if 'styles' in style['body']:
                            if 'style' in style['body']['styles']:
                                qml = style['body']['styles']['style']
                                self.create_qml(vlayer, qml)
        else:
            self.uri.setDataSource(schema_name, f'{tablename}', the_geom, None, field_id)
            vlayer = QgsVectorLayer(self.uri.uri(), f'{tablename}', 'postgres')
            self.check_for_group(vlayer, group)
            # The triggered function (action.triggered.connect(partial(...)) as the last parameter sends a boolean,
            # if we define style_id = None, style_id will take the boolean of the triggered action as a fault,
            # therefore, we define it with "-1"
            if style_id not in (None, "-1"):
                body = f'$${{"data":{{"style_id":"{style_id}"}}}}$$'
                style = self.controller.get_json('gw_fct_getstyle', body)
                if style['status'] == 'Failed': return
                if 'styles' in style['body']:
                    if 'style' in style['body']['styles']:
                        qml = style['body']['styles']['style']
                        self.create_qml(vlayer, qml)
        self.iface.mapCanvas().refresh()


    def create_qml(self, layer, style):

        main_folder = os.path.join(os.path.expanduser("~"), self.controller.plugin_name)
        config_folder = main_folder + os.sep + "temp" + os.sep
        if not os.path.exists(config_folder):
            os.makedirs(config_folder)
        path_temp_file = config_folder + 'temp_qml.qml'
        file = open(path_temp_file, 'w')
        file.write(style)
        file.close()
        del file
        self.load_qml(layer, path_temp_file)


    def check_for_group(self, layer, group=None):
        """ If the function receives a group name, check if it exists or not and put the layer in this group
        :param layer: (QgsVectorLayer)
        :param group: Name of the group that will be created in the toc (string)
        """

        if group is None:
            QgsProject.instance().addMapLayer(layer)
        else:
            QgsProject.instance().addMapLayer(layer, False)
            root = QgsProject.instance().layerTreeRoot()
            my_group = root.findGroup(group)
            if my_group is None:
                my_group = root.insertGroup(0, group)
            my_group.insertLayer(0, layer)


    def add_temp_layer(self, dialog, data, layer_name, force_tab=True, reset_text=True, tab_idx=1, del_old_layers=True,
                       group='GW Temporal Layers', disable_tabs=True):
        """ Add QgsVectorLayer into TOC
        :param dialog:
        :param data:
        :param layer_name:
        :param force_tab:
        :param reset_text:
        :param tab_idx:
        :param del_old_layers:
        :param group:
        :param disable_tabs: set all tabs, except the last, enabled or disabled (boolean).
        :return: Dictionary with text as result of previuos data (String), and list of layers added (QgsVectorLayer).
        """

        text_result = None
        temp_layers_added = []
        srid = global_vars.srid
        for k, v in list(data.items()):
            if str(k) == "info":
                text_result = self.populate_info_text(dialog, data, force_tab, reset_text, tab_idx, disable_tabs)
            elif k in ('point', 'line', 'polygon'):
                if 'values' in data[k]:
                    key = 'values'
                elif 'features' in data[k]:
                    key = 'features'
                else:
                    continue
                counter = len(data[k][key])
                if counter > 0:
                    counter = len(data[k][key])
                    geometry_type = data[k]['geometryType']
                    try:
                        if not layer_name:
                            layer_name = data[k]['layerName']
                    except KeyError:
                        layer_name = 'Temporal layer'
                    if del_old_layers:
                        self.delete_layer_from_toc(layer_name)
                    v_layer = QgsVectorLayer(f"{geometry_type}?crs=epsg:{srid}", layer_name, 'memory')
                    layer_name = None
                    # TODO This if controls if the function already works with GeoJson or is still to be refactored
                    # once all are refactored the if should be: if 'feature' not in data [k]: continue
                    if key == 'values':
                        self.populate_vlayer_old(v_layer, data, k, counter, group)
                    elif key == 'features':
                        self.populate_vlayer(v_layer, data, k, counter, group)
                    if 'qmlPath' in data[k] and data[k]['qmlPath']:
                        qml_path = data[k]['qmlPath']
                        self.load_qml(v_layer, qml_path)
                    elif 'category_field' in data[k] and data[k]['category_field']:
                        cat_field = data[k]['category_field']
                        size = data[k]['size'] if 'size' in data[k] and data[k]['size'] else 2
                        color_values = {'NEW': QColor(0, 255, 0), 'DUPLICATED': QColor(255, 0, 0),
                                        'EXISTS': QColor(240, 150, 0)}
                        self.categoryze_layer(v_layer, cat_field, size, color_values)
                    else:
                        if geometry_type == 'Point':
                            v_layer.renderer().symbol().setSize(3.5)
                            v_layer.renderer().symbol().setColor(QColor("red"))
                        elif geometry_type == 'LineString':
                            v_layer.renderer().symbol().setWidth(1.5)
                            v_layer.renderer().symbol().setColor(QColor("red"))
                        v_layer.renderer().symbol().setOpacity(0.7)
                    temp_layers_added.append(v_layer)
                    self.iface.layerTreeView().refreshLayerSymbology(v_layer.id())
        return {'text_result': text_result, 'temp_layers_added': temp_layers_added}


    def categoryze_layer(self, layer, cat_field, size, color_values, unique_values=None):
        """
        :param layer: QgsVectorLayer to be categorized (QgsVectorLayer)
        :param cat_field: Field to categorize (string)
        :param size: Size of feature (integer)
        """

        # get unique values
        fields = layer.fields()
        fni = fields.indexOf(cat_field)
        if not unique_values:
            unique_values = layer.dataProvider().uniqueValues(fni)
        categories = []

        for unique_value in unique_values:
            # initialize the default symbol for this geometry type
            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            if type(symbol) in (QgsLineSymbol, ):
                symbol.setWidth(size)
            else:
                symbol.setSize(size)

            # configure a symbol layer
            try:
                color = color_values.get(str(unique_value))
                symbol.setColor(color)
            except Exception:
                color = QColor(randrange(0, 256), randrange(0, 256), randrange(0, 256))
                symbol.setColor(color)

            # create renderer object
            category = QgsRendererCategory(unique_value, symbol, str(unique_value))
            # entry for the list of category items
            categories.append(category)

            # create renderer object
        renderer = QgsCategorizedSymbolRenderer(cat_field, categories)

        # assign the created renderer to the layer
        if renderer is not None:
            layer.setRenderer(renderer)

        layer.triggerRepaint()
        self.iface.layerTreeView().refreshLayerSymbology(layer.id())


    def populate_info_text(self, dialog, data, force_tab=True, reset_text=True, tab_idx=1, disable_tabs=True):
        """ Populate txt_infolog QTextEdit widget
        :param dialog: QDialog
        :param data: Json
        :param force_tab: Force show tab (boolean)
        :param reset_text: Reset(or not) text for each iteration (boolean)
        :param tab_idx: index of tab to force (integer)
        :param disable_tabs: set all tabs, except the last, enabled or disabled (boolean)
        :return: Text received from data (String)
        """

        change_tab = False
        text = tools_qt.getWidgetText(dialog, dialog.txt_infolog, return_string_null=False)

        if reset_text:
            text = ""
        for item in data['info']['values']:
            if 'message' in item:
                if item['message'] is not None:
                    text += str(item['message']) + "\n"
                    if force_tab:
                        change_tab = True
                else:
                    text += "\n"

        tools_qt.setWidgetText(dialog, 'txt_infolog', text + "\n")
        qtabwidget = dialog.findChild(QTabWidget, 'mainTab')
        if qtabwidget is not None:
            if change_tab and qtabwidget is not None:
                qtabwidget.setCurrentIndex(tab_idx)
            if disable_tabs:
                self.disable_tabs(dialog)

        return text


    def disable_tabs(self, dialog):
        """ Disable all tabs in the dialog except the log one and change the state of the buttons
        :param dialog: Dialog where tabs are disabled (QDialog)
        :return:
        """

        qtabwidget = dialog.findChild(QTabWidget, 'mainTab')
        for x in range(0, qtabwidget.count() - 1):
            qtabwidget.widget(x).setEnabled(False)

        btn_accept = dialog.findChild(QPushButton, 'btn_accept')
        if btn_accept:
            btn_accept.hide()

        btn_cancel = dialog.findChild(QPushButton, 'btn_cancel')
        if btn_cancel:
            tools_qt.setWidgetText(dialog, btn_accept, 'Close')


    def populate_vlayer(self, virtual_layer, data, layer_type, counter, group='GW Temporal Layers'):
        """
        :param virtual_layer: Memory QgsVectorLayer (QgsVectorLayer)
        :param data: Json
        :param layer_type: point, line, polygon...(string)
        :param counter: control if json have values (integer)
        :param group: group to which we want to add the layer (string)
        :return:
        """

        prov = virtual_layer.dataProvider()
        # Enter editing mode
        virtual_layer.startEditing()

        # Add headers to layer
        if counter > 0:
            for key, value in list(data[layer_type]['features'][0]['properties'].items()):
                if key == 'the_geom':
                    continue
                prov.addAttributes([QgsField(str(key), QVariant.String)])

        for feature in data[layer_type]['features']:
            geometry = self.get_geometry(feature)
            if not geometry:
                continue
            attributes = []
            fet = QgsFeature()
            fet.setGeometry(geometry)
            for key, value in feature['properties'].items():
                if key == 'the_geom':
                    continue
                attributes.append(value)

            fet.setAttributes(attributes)
            prov.addFeatures([fet])

        # Commit changes
        virtual_layer.commitChanges()
        QgsProject.instance().addMapLayer(virtual_layer, False)
        root = QgsProject.instance().layerTreeRoot()
        my_group = root.findGroup(group)
        if my_group is None:
            my_group = root.insertGroup(0, group)
        my_group.insertLayer(0, virtual_layer)


    def get_geometry(self, feature):
        """ Get coordinates from GeoJson and return QGsGeometry
        :param feature: feature to get geometry type and coordinates (GeoJson)
        :return: Geometry of the feature (QgsGeometry)
        functions  called in -> getattr(self, f"get_{feature['geometry']['type'].lower()}")(feature)
            def get_point(self, feature)
            get_linestring(self, feature)
            get_multilinestring(self, feature)
            get_polygon(self, feature)
            get_multipolygon(self, feature)
        """

        try:
            coordinates = getattr(self, f"get_{feature['geometry']['type'].lower()}")(feature)
            type_ = feature['geometry']['type']
            geometry = f"{type_}{coordinates}"
            return QgsGeometry.fromWkt(geometry)
        except AttributeError as e:
            self.controller.log_info(f"{type(e).__name__} --> {e}")
            return None


    def get_point(self, feature):
        """ Manage feature geometry when is Point
        :param feature: feature to get geometry type and coordinates (GeoJson)
        :return: Coordinates of the feature (String)
        This function is called in def get_geometry(self, feature)
              geometry = getattr(self, f"get_{feature['geometry']['type'].lower()}")(feature)
        """
        return f"({feature['geometry']['coordinates'][0]} {feature['geometry']['coordinates'][1]})"


    def get_linestring(self, feature):
        """ Manage feature geometry when is LineString
        :param feature: feature to get geometry type and coordinates (GeoJson)
        :return: Coordinates of the feature (String)
        This function is called in def get_geometry(self, feature)
              geometry = getattr(self, f"get_{feature['geometry']['type'].lower()}")(feature)
        """
        return self.get_coordinates(feature)


    def get_multilinestring(self, feature):
        """ Manage feature geometry when is MultiLineString
        :param feature: feature to get geometry type and coordinates (GeoJson)
        :return: Coordinates of the feature (String)
        This function is called in def get_geometry(self, feature)
              geometry = getattr(self, f"get_{feature['geometry']['type'].lower()}")(feature)
        """
        return self.get_multi_coordinates(feature)


    def get_polygon(self, feature):
        """ Manage feature geometry when is Polygon
        :param feature: feature to get geometry type and coordinates (GeoJson)
        :return: Coordinates of the feature (String)
        This function is called in def get_geometry(self, feature)
              geometry = getattr(self, f"get_{feature['geometry']['type'].lower()}")(feature)
        """
        return self.get_multi_coordinates(feature)


    def get_multipolygon(self, feature):
        """ Manage feature geometry when is MultiPolygon
        :param feature: feature to get geometry type and coordinates (GeoJson)
        :return: Coordinates of the feature (String)
        This function is called in def get_geometry(self, feature)
              geometry = getattr(self, f"get_{feature['geometry']['type'].lower()}")(feature)
        """

        coordinates = "("
        for coords in feature['geometry']['coordinates']:
            coordinates += "("
            for cc in coords:
                coordinates += "("
                for c in cc:
                    coordinates += f"{c[0]} {c[1]}, "
                coordinates = coordinates[:-2] + "), "
            coordinates = coordinates[:-2] + "), "
        coordinates = coordinates[:-2] + ")"
        return coordinates


    def get_coordinates(self, feature):
        """ Get coordinates of the received feature, to be a point
        :param feature: Json with the information of the received feature (geoJson)
        :return: Coordinates of the feature received (String)
        """

        coordinates = "("
        for coords in feature['geometry']['coordinates']:
            coordinates += f"{coords[0]} {coords[1]}, "
        coordinates = coordinates[:-2] + ")"
        return coordinates


    def get_multi_coordinates(self, feature):
        """ Get coordinates of the received feature, can be a line
        :param feature: Json with the information of the received feature (geoJson)
        :return: Coordinates of the feature received (String)
        """

        coordinates = "("
        for coords in feature['geometry']['coordinates']:
            coordinates += "("
            for c in coords:
                coordinates += f"{c[0]} {c[1]}, "
            coordinates = coordinates[:-2] + "), "
        coordinates = coordinates[:-2] + ")"
        return coordinates


    def populate_vlayer_old(self, virtual_layer, data, layer_type, counter, group='GW Temporal Layers'):
        """
        :param virtual_layer: Memory QgsVectorLayer (QgsVectorLayer)
        :param data: Json
        :param layer_type: point, line, polygon...(string)
        :param counter: control if json have values (integer)
        :param group: group to which we want to add the layer (string)
        :return:
        """

        prov = virtual_layer.dataProvider()

        # Enter editing mode
        virtual_layer.startEditing()
        if counter > 0:
            for key, value in list(data[layer_type]['values'][0].items()):
                # add columns
                if str(key) != 'the_geom':
                    prov.addAttributes([QgsField(str(key), QVariant.String)])

        # Add features
        for item in data[layer_type]['values']:
            attributes = []
            fet = QgsFeature()

            for k, v in list(item.items()):
                if str(k) != 'the_geom':
                    attributes.append(v)
                if str(k) in 'the_geom':
                    sql = f"SELECT St_AsText('{v}')"
                    row = self.controller.get_row(sql, log_sql=False)
                    if row and row[0]:
                        geometry = QgsGeometry.fromWkt(str(row[0]))
                        fet.setGeometry(geometry)
            fet.setAttributes(attributes)
            prov.addFeatures([fet])

        # Commit changes
        virtual_layer.commitChanges()
        QgsProject.instance().addMapLayer(virtual_layer, False)
        root = QgsProject.instance().layerTreeRoot()
        my_group = root.findGroup(group)
        if my_group is None:
            my_group = root.insertGroup(0, group)

        my_group.insertLayer(0, virtual_layer)


    def delete_layer_from_toc(self, layer_name):
        """ Delete layer from toc if exist
         :param layer_name: Name's layer (string)
        """

        layer = None
        for lyr in list(QgsProject.instance().mapLayers().values()):
            if lyr.name() == layer_name:
                layer = lyr
                break
        if layer is not None:
            # Remove layer
            QgsProject.instance().removeMapLayer(layer)

            # Remove group if is void
            root = QgsProject.instance().layerTreeRoot()
            group = root.findGroup('GW Temporal Layers')
            if group:
                layers = group.findLayers()
                if not layers:
                    root.removeChildNode(group)
            self.delete_layer_from_toc(layer_name)


    def load_qml(self, layer, qml_path):
        """ Apply QML style located in @qml_path in @layer
        :param layer: layer to set qml (QgsVectorLayer)
        :param qml_path: desired path (string)
        :return: True or False (boolean)
        """

        if layer is None:
            return False

        if not os.path.exists(qml_path):
            self.controller.log_warning("File not found", parameter=qml_path)
            return False

        if not qml_path.endswith(".qml"):
            self.controller.log_warning("File extension not valid", parameter=qml_path)
            return False

        layer.loadNamedStyle(qml_path)
        layer.triggerRepaint()

        return True
