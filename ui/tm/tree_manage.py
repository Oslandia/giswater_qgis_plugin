# -*- coding: utf-8 -*-
from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog
import os

FORM_CLASS, _ = uic.loadUiType(os.path.join(os.path.dirname(__file__), 'tree_manage.ui'))


class TreeManage(QDialog, FORM_CLASS):

    def __init__(self, parent=None):
        """ Constructor """
        super(TreeManage, self).__init__(parent)
        self.setupUi(self)

