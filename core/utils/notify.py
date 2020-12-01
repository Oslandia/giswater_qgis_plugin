"""
This file is part of Giswater 3
The program is free software: you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation, either version 3 of the License,
or (at your option) any later version.
"""
# -*- coding: utf-8 -*-
import json
import threading
from collections import OrderedDict

from ... import global_vars
from ...lib import tools_log, tools_db


class GwNotifyTools:
    # :var conn_failed: some times, when user click so fast 2 actions, LISTEN channel is stopped, and we need to
    #                   re-LISTEN all channels

    # Notify cannot use 'iface', directly or indirectly or open dialogs

    conn_failed = False
    list_channels = None

    def __init__(self):
        """ Class to control notify from PostgresSql """

        self.iface = global_vars.iface
        self.canvas = global_vars.canvas
        self.settings = global_vars.settings
        self.plugin_dir = global_vars.plugin_dir


    def start_listening(self, list_channels):
        """
        :param list_channels: List of channels to be listened
        """
        self.list_channels = list_channels
        for channel_name in list_channels:
            tools_db.execute_sql(f'LISTEN "{channel_name}";')

        thread = threading.Thread(target=self.wait_notifications)
        thread.start()


    def task_stopped(self, task):

        tools_log.log_info('Task "{name}" was cancelled'.format(name=task.description()))


    def task_completed(self, exception, result):
        """ Called when run is finished.
        Exception is not None if run raises an exception. Result is the return value of run
        """

        tools_log.log_info("task_completed")

        if exception is None:
            if result is None:
                msg = 'Completed with no exception and no result'
                tools_log.log_info(msg)
            else:
                tools_log.log_info('Task {name} completed\n'
                    'Total: {total} (with {iterations} '
                    'iterations)'.format(name=result['task'], total=result['total'],
                                         iterations=result['iterations']))
        else:
            tools_log.log_info("Exception: {}".format(exception))
            raise exception


    def stop_listening(self, list_channels):
        """
        :param list_channels: List of channels to be unlistened
        """

        for channel_name in list_channels:
            tools_db.execute_sql(f'UNLISTEN "{channel_name}";')


    def wait_notifications(self):

        try:
            if self.conn_failed:
                for channel_name in self.list_channels:
                    tools_db.execute_sql(f'LISTEN "{channel_name}";')

                self.conn_failed = False

            # Initialize thread
            thread = threading.Timer(interval=1, function=self.wait_notifications)
            thread.start()

            # Check if any notification to process
            dao = global_vars.dao
            dao.get_poll()

            last_paiload = None
            while dao.conn.notifies:
                notify = dao.conn.notifies.pop()
                msg = f'<font color="blue"><bold>Got NOTIFY: </font>'
                msg += f'<font color="black"><bold>{notify.pid}, {notify.channel}, {notify.payload} </font>'
                tools_log.log_info(msg)
                if notify.payload and notify.payload != last_paiload:
                    last_paiload = notify.payload
                    try:
                        complet_result = json.loads(notify.payload, object_pairs_hook=OrderedDict)
                        self.execute_functions(complet_result)
                    except Exception:
                        pass

        except AttributeError:
            self.conn_failed = True


    def execute_functions(self, complet_result):
        """
        functions called in -> getattr(global_vars.gw_infotools, function_name)(**params)
            def set_layer_index(self, **kwargs)
            def refresh_attribute_table(self, **kwargs)
            def refresh_canvas(self, **kwargs)
            def show_message(self, **kwargs)

        """

        for function in complet_result['functionAction']['functions']:
            function_name = function['name']
            params = function['parameters']
            try:
                # getattr(self, function_name)(**params)
                getattr(global_vars.gw_infotools, function_name)(**params)
            except AttributeError as e:
                # If function_name not exist as python function
                tools_log.log_warning(f"Exception error: {e}")