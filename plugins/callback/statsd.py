# -*- coding: utf-8 -*-
# (C) 2021, Mark Mercado <mamercad@gmail.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = """
author: Mark Mercado (@mamercad)
name: community.general.statsd
type: aggregate
requirements:
  - Enabling this callback plugin
  - StatsD infrastructure to collect the emitted metrics
short_description: Send Ansible playbook result metrics to a StatsD (or StatsD Prometheus Exporter) endpoint
description:
  - Send Ansible playbook result metrics to a StatsD (or StatsD Prometheus Exporter) endpoint
options:
  statsd_host:
    name: StatsD hostname or IP
    default: 127.0.0.1
    description: StatsD hostname or IP to send metrics to
    env:
      - name: STATSD_HOST
    ini:
      - section: callback_statsd
        key: statsd_host
  statsd_port:
    name: StatsD metrics port
    default: 9125
    description: StatsD TCP metrics ingestion port
    env:
      - name: STATSD_PORT
    ini:
      - section: callback_statsd
        key: statsd_port
"""

EXAMPLES = """
examples: >

  Example StatsD Prometheus Exporter mappings:

    - match: ansible.counter.stats.*.*.*.*
      match_metric_type: counter
      name: ansible_counter
      labels:
        event: "stats"
        type: "counter"
        basedir: "$1"
        playbook: "$2"
        result: "$3"
        host: "$4"

    - match: ansible.gauge.stats.*.*
      match_metric_type: gauge
      name: ansible_gauge
      labels:
        event: "stats"
        type: "gauge"
        basedir: "$1"
        playbook: "$2"

    - match: ansible.counter.*.*.*.*.*.*
      match_metric_type: counter
      name: ansible_counter
      labels:
        event: "task"
        type: "counter"
        basedir: "$1"
        playbook: "$2"
        play: "$3"
        task: "$4"
        host: "$5"
        result: "$6"

    - match: ansible.gauge.*.*.*.*.*.*
      match_metric_type: gauge
      name: ansible_gauge
      labels:
        event: "task"
        type: "gauge"
        basedir: "$1"
        playbook: "$2"
        play: "$3"
        task: "$4"
        host: "$5"
        result: "$6"

    - match: "."
      match_type: regex
      action: drop
      name: "dropped"
"""

import base64
import getpass
import uuid
import socket
from pprint import pprint

from datetime import datetime
from os.path import basename

from ansible.plugins.callback import CallbackBase
from ansible.executor.task_result import TaskResult
from ansible.executor.stats import AggregateStats


class StatsD(object):
    def __init__(self, statsd_host, statsd_port):
        self.statsd_host = statsd_host
        self.statsd_port = int(statsd_port)
        self.ansible_check_mode = True
        self.ansible_basedir = ""
        self.ansible_playbook = ""
        self.ansible_plays = []
        # self.ansible_version = ""
        # self.session = str(uuid.uuid4())
        # self.host = socket.gethostname()
        # self.ip_address = socket.gethostbyname(socket.gethostname())
        # self.user = getpass.getuser()

    def send_metric(self, metric):
        if not self.ansible_check_mode:
            statsd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            statsd.connect((self.statsd_host, self.statsd_port))
            statsd.sendall(metric.encode())
            statsd.close()


class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = "aggregate"
    CALLBACK_NAME = "community.general.statsd"
    CALLBACK_NEEDS_WHITELIST = True

    def __init__(self, display=None):
        super(CallbackModule, self).__init__(display=display)
        self.start_datetimes = {}
        self.start_datetimes["playbook"] = {}
        self.start_datetimes["play"] = {}
        self.start_datetimes["task"] = {}

    def set_options(self, task_keys=None, var_options=None, direct=None):
        super(CallbackModule, self).set_options(
            task_keys=task_keys, var_options=var_options, direct=direct
        )
        self.statsd_host = self.get_option("statsd_host")
        self.statsd_port = self.get_option("statsd_port")

        if self.statsd_host is None:
            self.disabled = True
            self._display.warning(
                "StatsD host not found; please define"
                "`STATSD_HOST` in the environment"
                "or in ansible.cfg"
            )

        if self.statsd_port is None:
            self.disabled = True
            self._display.warning(
                "StatsD port not found; please define"
                "`STATSD_PORT` in the environment"
                "or in ansible.cfg"
            )

        self.statsd = StatsD(self.statsd_host, self.statsd_port)

        if self._display.verbosity:
            self._display.display(
                f"statsd_host {self.statsd_host}\n" f"statsd_port {self.statsd_port}"
            )

    def _runtime(self, result):
        if isinstance(result, AggregateStats):
            return (
                datetime.utcnow() - self.start_datetimes["playbook"]
            ).total_seconds()
        if isinstance(result, TaskResult):
            return (
                datetime.utcnow() - self.start_datetimes["task"][result._task._uuid]
            ).total_seconds()

    def v2_playbook_on_start(self, playbook):
        self.start_datetimes["playbook"] = datetime.utcnow()
        # self.statsd.ansible_basedir = base64.b64encode(playbook._basedir.encode("utf-8")).decode("utf-8")
        self.statsd.ansible_basedir = playbook._basedir.replace(".", "_")
        self.statsd.ansible_playbook = basename(playbook._file_name).split(".")[0]
        self.statsd.ansible_plays = playbook.get_plays()

        if self._display.verbosity:
            self._display.display(
                "== v2_playbook_on_start ==\n"
                f"ansible_basedir {self.statsd.ansible_basedir}\n"
                f"ansible_playbook {self.statsd.ansible_playbook}"
            )

    def v2_playbook_on_play_start(self, play):
        self.start_datetimes["play"] = datetime.utcnow()
        if self._display.verbosity:
            self._display.display("== v2_on_play_start ==\n")
            self._display.display(str(play))
        self.statsd.ansible_play = str(play)

    def v2_playbook_on_task_start(self, task, is_conditional):
        self.start_datetimes["task"][task._uuid] = datetime.utcnow()
        if self._display.verbosity:
            self._display.display(
                "== v2_playbook_on_task_start ==\n" f"task uuid {task._uuid}"
            )
        self.statsd.ansible_task = str(task.get_name())

    def v2_playbook_on_handler_task_start(self, task, is_conditional):
        self.start_datetimes["task"][task._uuid] = datetime.utcnow()
        if self._display.verbosity:
            self._display.display(
                "== v2_playbook_on_handler_task_start ==\n" f"task_uuid {task._uuid}"
            )

    def v2_runner_on_ok(self, result, **kwargs):
        self.statsd.ansible_check_mode = result._task_fields.get("check_mode", True)
        runtime = self._runtime(result)
        host = result._host
        counter = f"ansible.counter.{self.statsd.ansible_basedir}.{self.statsd.ansible_playbook}.{self.statsd.ansible_play}.{self.statsd.ansible_task}.{host}.ok:1|c"
        gauge = f"ansible.gauge.{self.statsd.ansible_basedir}.{self.statsd.ansible_playbook}.{self.statsd.ansible_play}.{self.statsd.ansible_task}.{host}.ok:{runtime}|g"
        if self._display.verbosity:
            self._display.display(
                "== v2_runner_on_ok ==\n"
                f"task runtime {runtime}\n"
                "counter ansible.counter.[basedir].[playbook].[play].[task].[host].ok:1|c\n"
                f"counter {counter}\n"
                "gauge ansible.gauge.[basedir].[playbook].[play].[task].[host].ok:[runtime]|g\n"
                f"gauge {gauge}"
            )
        self.statsd.send_metric(counter)
        self.statsd.send_metric(gauge)

    def v2_runner_on_skipped(self, result, **kwargs):
        self.statsd.ansible_check_mode = result._task_fields.get("check_mode", True)
        runtime = self._runtime(result)
        host = result._host
        counter = f"ansible.counter.{self.statsd.ansible_basedir}.{self.statsd.ansible_playbook}.{self.statsd.ansible_play}.{self.statsd.ansible_task}.{host}.skipped:1|c"
        gauge = f"ansible.gauge.{self.statsd.ansible_basedir}.{self.statsd.ansible_playbook}.{self.statsd.ansible_play}.{self.statsd.ansible_task}.{host}.skipped:{runtime}|g"
        if self._display.verbosity:
            self._display.display(
                "== v2_runner_on_skipped ==\n"
                f"task runtime {runtime}\n"
                "counter ansible.counter.[basedir].[playbook].[play].[task].[host].skipped:1|c\n"
                f"counter {counter}\n"
                "gauge ansible.gauge.[basedir].[playbook].[play].[task].[host].skipped:[runtime]|g\n"
                f"gauge {gauge}"
            )
        self.statsd.send_metric(counter)
        self.statsd.send_metric(gauge)

    def v2_runner_on_failed(self, result, **kwargs):
        self.statsd.ansible_check_mode = result._task_fields.get("check_mode", True)
        runtime = self._runtime(result)
        host = result._host
        counter = f"ansible.counter.{self.statsd.ansible_basedir}.{self.statsd.ansible_playbook}.{self.statsd.ansible_play}.{self.statsd.ansible_task}.{host}.failed:1|c"
        gauge = f"ansible.gauge.{self.statsd.ansible_basedir}.{self.statsd.ansible_playbook}.{self.statsd.ansible_play}.{self.statsd.ansible_task}.{host}.failed:{runtime}|g"
        if self._display.verbosity:
            self._display.display(
                "== v2_runner_on_failed ==\n"
                f"task runtime {runtime}\n"
                "counter ansible.counter.[basedir].[playbook].[play].[task].[host].failed:1|c\n"
                f"counter {counter}\n"
                "gauge ansible.gauge.[basedir].[playbook].[play].[task].[host].failed:[runtime]|g\n"
                f"gauge {gauge}"
            )
        self.statsd.send_metric(counter)
        self.statsd.send_metric(gauge)

    def v2_runner_on_async_failed(self, result, **kwargs):
        self.statsd.ansible_check_mode = result._task_fields.get("check_mode", True)
        runtime = self._runtime(result)
        host = result._host
        counter = f"ansible.counter.{self.statsd.ansible_basedir}.{self.statsd.ansible_playbook}.{self.statsd.ansible_play}.{self.statsd.ansible_task}.{host}.async_failed:1|c"
        gauge = f"ansible.gauge.{self.statsd.ansible_basedir}.{self.statsd.ansible_playbook}.{self.statsd.ansible_play}.{self.statsd.ansible_task}.{host}.async_failed:{runtime}|g"
        if self._display.verbosity:
            self._display.display(
                "== v2_runner_on_async_failed ==\n"
                f"task runtime {runtime}\n"
                "counter ansible.counter.[basedir].[playbook].[play].[task].[host].async_failed:1|c\n"
                f"counter {counter}\n"
                "gauge ansible.gauge.[basedir].[playbook].[play].[task].[host].async_failed:[runtime]|g\n"
                f"gauge {gauge}"
            )
        self.statsd.send_metric(counter)
        self.statsd.send_metric(gauge)

    def v2_runner_on_unreachable(self, result, **kwargs):
        self.statsd.ansible_check_mode = result._task_fields.get("check_mode", True)
        runtime = self._runtime(result)
        host = result._host
        counter = f"ansible.counter.{self.statsd.ansible_basedir}.{self.statsd.ansible_playbook}.{self.statsd.ansible_play}.{self.statsd.ansible_task}.{host}.unreachable:1|c"
        gauge = f"ansible.gauge.{self.statsd.ansible_basedir}.{self.statsd.ansible_playbook}.{self.statsd.ansible_play}.{self.statsd.ansible_task}.{host}.unreachable:{runtime}|g"
        if self._display.verbosity:
            self._display.display(
                "== v2_runner_on_unreachable ==\n"
                f"task runtime {runtime}\n"
                "counter ansible.counter.[basedir].[playbook].[play].[task].[host].unreachable:1|c\n"
                f"counter {counter}\n"
                "gauge ansible.gauge.[basedir].[playbook].[play].[task].[host].unreachable:[runtime]|g\n"
                f"gauge {gauge}"
            )
        self.statsd.send_metric(counter)
        self.statsd.send_metric(gauge)

    def v2_playbook_on_stats(self, stats):
        runtime = self._runtime(stats)

        # counter = f"ansible.counter.{self.statsd.ansible_basedir}.{self.statsd.ansible_playbook}.stats:1|c"
        # gauge = f"ansible.gauge.{self.statsd.ansible_basedir}.{self.statsd.ansible_playbook}.stats:{runtime}|g"

        # if self._display.verbosity:
        #     self._display.display("== v2_runner_on_stats ==\n"
        #                          f"playbook runtime {runtime}\n"
        #                           "counter ansible.counter.[basedir].[playbook].stats:1|c\n"
        #                          f"counter {counter}\n"
        #                           "gauge ansible.gauge.[basedir].[playbook].stats.[runtime]|g\n"
        #                          f"gauge {gauge}")

        # self.statsd.send_metric(counter)
        # self.statsd.send_metric(gauge)

        s = dict(stats.__dict__)
        for k1 in s.keys():
            if len(s[k1]):
                for k2 in s[k1].keys():
                    counter = "ansible.counter.stats.{0}.{1}.{2}.{3}:1|c".format(
                        self.statsd.ansible_basedir,
                        self.statsd.ansible_playbook,
                        k1,
                        k2,
                    )
                    gauge = "ansible.gauge.stats.{0}.{1}:{2}|g".format(
                        self.statsd.ansible_basedir,
                        self.statsd.ansible_playbook,
                        runtime,
                    )

                    if self._display.verbosity:
                        self._display.display(
                            "== v2_runner_on_stats ==\n"
                            f"playbook runtime {runtime}\n"
                            "counter ansible.counter.[basedir].[playbook].[result].[hostname]:1|c\n"
                            f"counter {counter}\n"
                            "gauge ansible.gauge.[basedir].[playbook]:[runtime]|g\n"
                            f"gauge {gauge}"
                        )

                    self.statsd.send_metric(counter)
                    self.statsd.send_metric(gauge)
