#!/usr/bin/python3
# -*- coding:utf-8 -*-

"""
PyocdGUIClient
"""
__author__ = "george"
__date__ = "2024/09/23 20:20"
__version__ = "1.0.0"

import os
from configparser import ConfigParser
import logging
import time
import dearpygui.dearpygui as dpg
import ctypes
import platform
import os
import sys
from time import sleep
from pyocd.core.helpers import ConnectHelper
from pyocd.tools.lists import ListGenerator
import colorama
import prettytable
from typing import (Any, Dict, List, Optional, Type,Iterable,Tuple,Sequence)

from pyocd.core.session import Session
from pyocd.target.pack import pack_target
from pyocd.flash.eraser import FlashEraser
from pathlib import Path
from pyocd.flash.file_programmer import FileProgrammer

from pyocd.core.soc_target import SoCTarget
from pyocd.debug.rtt import RTTControlBlock, RTTUpChannel, RTTDownChannel
from pyocd.subcommands.base import SubcommandBase
from pyocd.utility.cmdline import convert_session_options, int_base_0
from pyocd.utility.kbhit import KBHit
import threading
from pyocd.probe.aggregator import PROBE_CLASSES
from pyocd.probe.cmsis_dap_probe import CMSISDAPProbe
PROBE_CLASSES["cmsisdap"] = CMSISDAPProbe

#from pyocd.utility.progress import (print_progress)

LOG = logging.getLogger(__name__)
DEFAULT_LOG_LEVEL = logging.WARNING

#配置文件
file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")
cf = ConfigParser()
cf.read('config.ini', encoding='utf-8')

def save_config(key,value):
    cf.read('config.ini', encoding='utf-8')
    if not cf.has_section('pyocd'):
        cf.add_section('pyocd')
    cf.set('pyocd', key, value)
    cf.write(open(file_path, 'w+'))
def read_config(key)->str:
    #cf.read('config.ini', encoding='utf-8')
    return cf.get('pyocd', key,fallback="")


#UI界面
window_width = 800
window_height = 600  

ID_MENU_ADD_PACK = 0x1000
ID_MENU_SHOW_PACK = 0x1001
ID_MENU_CLEAN_PACK = 0x1001

def resource_path(relative_path):
    if getattr(sys, 'frozen', False): #是否Bundle Resource
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def UsePlatform( ):
    global window_height 
    global window_width
    sysstr = platform.system()
    if(sysstr =="Windows"):
        print ("Call Windows tasks")
        user32 = ctypes.windll.user32
        window_width = user32.GetSystemMetrics(0)
        window_height = user32.GetSystemMetrics(1)
        print ("window_width %d window_height %d"%(window_width,window_height))
    elif(sysstr == "Linux"):
        print ("Call Linux tasks")
    else:
        print ("Other System tasks")
#end

def del_progress():
    time.sleep(0.2)

def progress_print(total_cnt=20, index_cha='+', pro_total_cnt=50, fun=None):
     
    """
    :param total_cnt: 总循环次数
    :param index_cha: 进度指示符号，可以任意替换喜欢的符号
    :param pro_total_cnt: 100%进度显示的总符号个数
    :param fun: 每次进度循环处理的回调函数
    """
    star_time = time.time()
    for i in range(total_cnt):
        current_cnt = int((i + 1) / total_cnt * pro_total_cnt)
        str_progress = index_cha * current_cnt + ' ' * (pro_total_cnt - current_cnt)
        spend_time = time.time() - star_time
        print("\033[31m\r{:.1%} [{}] total time: {:.2f}s\033[0m".format((i + 1) / total_cnt, str_progress, spend_time),
                end="", flush=True)
        if fun is not None:
            fun()
    print()
def print_devices():
    allProbes = ConnectHelper.get_all_connected_probes(blocking=False)
    if len(allProbes):
        #ConnectHelper._print_probe_list(allProbes)
        get_probe_list(allProbes)
    else:
        print(colorama.Fore.RED + "No available debug probes are connected" + colorama.Style.RESET_ALL)
    print(colorama.Style.RESET_ALL, end='')

def get_probe_list(probes: Sequence["DebugProbe"]) -> None:

    for index, probe in enumerate(probes):
        board_info = probe.associated_board_info
        print("probe.description %s ",probe.description)
        # pt.add_row([
        #     colorama.Fore.MAGENTA + str(index),
        #     colorama.Fore.GREEN + probe.description,
        #     colorama.Fore.CYAN + probe.unique_id,
        #     target_type_desc,
        #     ])
        # if board_info:
        #     pt.add_row([
        #         "",
        #         (colorama.Fore.YELLOW + (board_info.vendor or board_info.name)) if board_info else dim_dash,
        #         (colorama.Fore.YELLOW + board_info.name) if (board_info and board_info.vendor) else "",
        #         "",
        #         ])
    

def _get_pretty_table( fields: List[str], header: bool = None) -> prettytable.PrettyTable:
        """@brief Returns a PrettyTable object with formatting options set."""
        pt = prettytable.PrettyTable(fields)
        pt.align = 'l'
        if header is not None:
            pt.header = header
        else:
            pt.header = True
        pt.border = True
        pt.hrules = prettytable.HEADER
        pt.vrules = prettytable.NONE
        return pt

def print_targets():
    obj = ListGenerator.list_targets(name_filter=None,
                                            vendor_filter=None,
                                            source_filter=None)
    pt = _get_pretty_table(["Name", "Vendor", "Part Number", "Families", "Source"])
    for info in sorted(obj['targets'], key=lambda i: i['name']):
        pt.add_row([
                    info['name'],
                    info['vendor'],
                    info['part_number'],
                    ', '.join(info['part_families']),
                    info['source'],
                    ])
    print(pt)

def convert_one_session_option(name: str, value: Optional[str]) -> Tuple[str, Any]:
    """@brief Convert one session option's value from a string.

    Handles "no-" prefixed option names by inverting their boolean value. If a non-boolean option has
    a "no-" prefix, then a warning is logged and None returned for the value.

    @return Bi-tuple of option name, converted value. The option name may be modified from the one passed
        in for cases like a "no-" prefix.
    """
    # Check for and strip "no-" prefix before we validate the option name.
    if name.startswith('no-'):
        name = name[3:]
        had_no_prefix = True
    else:
        had_no_prefix = False

    # Look up this option.
    try:
        info = OPTIONS_INFO[name]
    except KeyError:
        # Return the value unmodified for unknown options.
        LOG.warning("unknown session option '%s'", name)
        return name, value

    # Check if "no-" prefix is allowed. Only bool options can use it.
    if had_no_prefix and (info.type is not bool):
        LOG.warning("'no-' prefix used on non-boolean session option '%s'", name)
        return name, None

    # Check for a special converter function.
    if name in _OPTION_CONVERTERS:
        return name, _OPTION_CONVERTERS[name](value)

    # Default result; unset option value.
    result = None

    # Extract the option's type. If its type is a tuple of types, then take the first type.
    if isinstance(info.type, tuple):
        option_type = cast(tuple, info.type)[0]
    else:
        option_type = info.type

    # Handle bool options without a value specially.
    if value is None:
        if issubclass(option_type, bool):
            result = not had_no_prefix
        else:
            LOG.warning("non-boolean option '%s' requires a value", name)
    # Convert string value to option type.
    elif issubclass(option_type, bool):
        if value.lower() in ("true", "1", "yes", "on", "false", "0", "no", "off"):
            result = value.lower() in ("true", "1", "yes", "on")

            # If a bool option with "no-" prefix has a value, the value is inverted.
            if had_no_prefix:
                result = not result
        else:
            LOG.warning("invalid value for option '%s'", name)
    elif issubclass(option_type, int):
        try:
            result = int(value, base=0)
        except ValueError:
            LOG.warning("invalid value for option '%s'", name)
    elif issubclass(option_type, float):
        try:
            result = float(value)
        except ValueError:
            LOG.warning("invalid value for option '%s'", name)
    else:
        result = value

    return name, result


def convert_session_options(option_list: Iterable[str]) -> Dict[str, Any]:
    """@brief Convert a list of session option settings to a dictionary."""
    options = {}
    if option_list is not None:
        for o in option_list:
            if '=' in o:
                name, value = o.split('=', 1)
                name = name.strip().lower()
                value = value.strip()
            else:
                name = o.strip().lower()
                value = None

            name, value = convert_one_session_option(name, value)
            if value is not None:
                options[name] = value
    return options
def print_pack_targets():
    session = Session(None,
                        project_dir=None,
                        config_file=None,
                        no_config=None,
                        pack=r'D:\work\MCU\software\Nationstech.N32G45x_DFP.1.0.1.pack', 
                        **convert_session_options(None)
                        )

    if session.options['pack'] is not None:
        pack_target.PackTargets.populate_targets_from_pack(session.options['pack'])


def erase_targets():
    session = ConnectHelper.session_with_chosen_probe(
                        project_dir=None,
                        config_file=None,
                        user_script=None,
                        no_config=None,
                        pack=r'D:\work\MCU\software\Nationstech.N32G45x_DFP.1.0.1.pack', 
                        unique_id=None,
                        blocking=(not None),
                        connect_mode=None,
                        options = {"frequency": 4000000, "target_override": "n32g455rcl7"},
                        option_defaults=None,
                        )
    if session is None:
        LOG.error("No device available to erase")
        return 1
    with session:
        #mode = self._args.erase_mode or FlashEraser.Mode.SECTOR
        eraser = FlashEraser(session, FlashEraser.Mode.CHIP)

        #addresses = flatten_args(self._args.addresses)
        eraser.erase(None)

def print_progress(progress):
    print(progress)
    dpg.set_value("flash_progress_bar", progress)

class RTTThread:
    def __init__(self):
        self.thread = None
        self.alive = threading.Event()
    
    def StartThread(self):
        """Start the receiver thread"""
        self.thread = threading.Thread(target=self.ComPortThread)
        self.thread.daemon = True
        self.alive.set()
        self.thread.start()
    def StopThread(self):
        """Stop the receiver thread, wait until it's finished."""
        if self.thread is not None:
            self.alive.clear()          # clear alive event for thread
            self.thread.join()          # wait until thread has finished
            self.thread = None
    def DisConnect(self):
        self.StopThread()

    def Connect(self):
        #todo:
        self.StartThread()
        self.alive.set()
    def viewer_loop(self,up_chan, down_chan, kb):
        # byte array to send via RTT
        cmd = bytes()
        log_buff = ''
        while self.alive.is_set():
            # poll at most 1000 times per second to limit CPU use
            sleep(0.001)

            # read data from up buffer 0 (target -> host) and write to
            # stdout
            try:
                up_data: bytes = up_chan.read()
                log_buff = log_buff + str(up_data, encoding = "utf-8") 
                #dpg.configure_item("tty_text",default_value = log_buff)
                dpg.set_value("rtt_log", log_buff)
            except:
                break
        
            #sys.stdout.buffer.write(up_data)
            #sys.stdout.buffer.flush()
            #print(up_data, end="", flush=True)

            # try to fetch character
            if kb.kbhit():
                c: str = kb.getch()

                if ord(c) == 27: # process ESC
                    break
                elif c.isprintable() or c == '\n':
                    print(c, end="", flush=True)

                # add char to buffer
                cmd += c.encode("utf-8")

            # write buffer to target
            if not cmd:
                continue

            # write cmd buffer to down buffer 0 (host -> target)
            bytes_out = down_chan.write(cmd)
            cmd = cmd[bytes_out:]

    def ComPortThread(self):
        print("ComPortThread Start----")
        session = None
        kb = None
        pack_path = dpg.get_value("pack_path");
        print("pack_path\n")
        if len(pack_path)==0 :
            pack_path = None
        target_name = dpg.get_value("target_name");
        if len(target_name)==0 :
            target_name = None
        try:
            session = ConnectHelper.session_with_chosen_probe(
                pack=pack_path,
                target_override=target_name,
                options=convert_session_options(None),
                )

            if session is None:
                LOG.error("No target device available")
                return 1

            with session:

                target: SoCTarget = session.board.target

                control_block = RTTControlBlock.from_target(target)
                control_block.start()

                if len(control_block.up_channels) < 1:
                    LOG.error("No up channels.")
                    return 1

                LOG.info(f"{len(control_block.up_channels)} up channels and "
                            f"{len(control_block.down_channels)} down channels found")

                up_chan: RTTUpChannel = control_block.up_channels[0]
                up_name = up_chan.name if up_chan.name is not None else ""
                LOG.info(f"Reading from up channel {0} (\"{up_name}\")")

                # some targets might need this here
                #target.reset_and_halt()

                target.resume()

                # set up terminal input
                kb = KBHit()

                if len(control_block.down_channels) < 1:
                    LOG.error("No down channels.")
                    return 1
                down_chan: RTTDownChannel = control_block.down_channels[0]
                down_name = down_chan.name if down_chan.name is not None else ""
                LOG.info(f"Writing to down channel {0} (\"{down_name}\")")

                self.viewer_loop(up_chan, down_chan, kb)
                print("RTT closed")

        except KeyboardInterrupt:
            pass

        finally:
            if session:
                session.close()
            if kb:
                kb.set_normal_term()

        print("ComPortThread Over----")#读一个字节
        

def viewer_loop(up_chan, down_chan, kb):
    # byte array to send via RTT
    cmd = bytes()
    log_buff = ''
    while not True:
        # poll at most 1000 times per second to limit CPU use
        sleep(0.001)

        # read data from up buffer 0 (target -> host) and write to
        # stdout
        try:
            up_data: bytes = up_chan.read()
            log_buff = log_buff + str(up_data, encoding = "utf-8") 
            #dpg.configure_item("tty_text",default_value = log_buff)
            dpg.set_value("rtt_log", log_buff)
        except:
            break
       
        #sys.stdout.buffer.write(up_data)
        #sys.stdout.buffer.flush()
        #print(up_data, end="", flush=True)

        # try to fetch character
        if kb.kbhit():
            c: str = kb.getch()

            if ord(c) == 27: # process ESC
                break
            elif c.isprintable() or c == '\n':
                print(c, end="", flush=True)

            # add char to buffer
            cmd += c.encode("utf-8")

        # write buffer to target
        if not cmd:
            continue

        # write cmd buffer to down buffer 0 (host -> target)
        bytes_out = down_chan.write(cmd)
        cmd = cmd[bytes_out:]

def open_rtt():

    session = None
    kb = None
    pack_path = dpg.get_value("pack_path");
    print("pack_path\n")
    if len(pack_path)==0 :
        pack_path = None
    target_name = dpg.get_value("target_name");
    if len(target_name)==0 :
        target_name = None
    try:
        session = ConnectHelper.session_with_chosen_probe(
            pack=pack_path,
            target_override=target_name,
            options=convert_session_options(None),
            )

        if session is None:
            LOG.error("No target device available")
            return 1

        with session:

            target: SoCTarget = session.board.target

            control_block = RTTControlBlock.from_target(target)
            control_block.start()

            if len(control_block.up_channels) < 1:
                LOG.error("No up channels.")
                return 1

            LOG.info(f"{len(control_block.up_channels)} up channels and "
                        f"{len(control_block.down_channels)} down channels found")

            up_chan: RTTUpChannel = control_block.up_channels[0]
            up_name = up_chan.name if up_chan.name is not None else ""
            LOG.info(f"Reading from up channel {0} (\"{up_name}\")")

            # some targets might need this here
            #target.reset_and_halt()

            target.resume()

            # set up terminal input
            kb = KBHit()

            if len(control_block.down_channels) < 1:
                LOG.error("No down channels.")
                return 1
            down_chan: RTTDownChannel = control_block.down_channels[0]
            down_name = down_chan.name if down_chan.name is not None else ""
            LOG.info(f"Writing to down channel {0} (\"{down_name}\")")

            viewer_loop(up_chan, down_chan, kb)
            print("RTT closed")

    except KeyboardInterrupt:
        pass

    finally:
        if session:
            session.close()
        if kb:
            kb.set_normal_term()

    return 0

def load_targets():
    session = ConnectHelper.session_with_chosen_probe(
                        project_dir=None,
                        config_file=None,
                        user_script=None,
                        no_config=None,
                        pack=r'D:\work\MCU\software\Nationstech.N32G45x_DFP.1.0.1.pack', 
                        unique_id=None,
                        blocking=(not None),
                        connect_mode=None,
                        options = {"frequency": 4000000, "target_override": "n32g455rcl7"},
                        option_defaults=None,
                        )
    with session:
        programmer = FileProgrammer(session,progress=print_progress,
                        chip_erase=None,
                        no_reset=None)
        filename = r'E:\MCU\code\nationstech\lt9211-bba-box\Project\TargetFile\Target.bin'
        # Get an initial path with the argument as-is.
        file_path = Path(filename).expanduser()

        # Look for a base address suffix. If the supplied argument including an address suffix
        # references an existing file, then the address suffix is not extracted.
        base_address = None

        # Resolve our path.
        file_path = Path(filename).expanduser().resolve()
        filename = str(file_path)

        if base_address is None:
            LOG.info("Loading %s", filename)
        else:
            LOG.info("Loading %s at %#010x", filename, base_address)

        programmer.program(filename,
                        base_address=0x8000000,
                        file_format=None)
def _on_demo_close(sender, app_data, user_data):
    rttThread.DisConnect()
    dpg.delete_item(sender)

def menu_callback(sender, app_data, user_data):
        print(f"sender: {sender}, \t app_data: {app_data}, \t user_data: {user_data}")
        if sender ==    ID_MENU_ADD_PACK:
                print("add pack")
        elif sender == ID_MENU_SHOW_PACK:
                print("show pack")
        elif sender == ID_MENU_CLEAN_PACK:
                print("clean pack")
def show_target(sender, app_data):
    print('show_target.')
    print("Sender: ", sender)
    print("App Data: ", app_data)
    pack_path = dpg.get_value("pack_path");
    print("pack_path\n")
    if len(pack_path)==0 :
        pack_path = None
    session = Session(None,
                        project_dir=None,
                        config_file=None,
                        no_config=None,
                        pack=pack_path, 
                        **convert_session_options(None)
                        )

    if session.options['pack'] is not None:
        pack_target.PackTargets.populate_targets_from_pack(session.options['pack'])
    obj = ListGenerator.list_targets(name_filter=None,
                                            vendor_filter=None,
                                            source_filter=None)
    
    for info in sorted(obj['targets'], key=lambda i: i['name']):
        with dpg.table_row(parent="pack_table"):
            dpg.add_selectable(label=info['name'], span_columns=True, callback=clb_selectable, user_data=info['name'])
            dpg.add_selectable(label=info['vendor'], span_columns=True, callback=clb_selectable, user_data=info['name'])
            dpg.add_selectable(label=info['part_number'], span_columns=True, callback=clb_selectable, user_data=info['name'])
            dpg.add_selectable(label=', '.join(info['part_families']), span_columns=True, callback=clb_selectable, user_data=info['name'])
            dpg.add_selectable(label=info['source'], span_columns=True, callback=clb_selectable, user_data=info['name'])
        

def pack_callback(sender, app_data):
    print('OK was clicked.')
    print("Sender: ", sender)
    print("App Data: ", app_data)
    dpg.set_value("pack_path", app_data['file_path_name'])
    save_config("pack_path",app_data['file_path_name'])

def intput_callback(sender, app_data, user_data):
    print(f"sender is: {sender}")
    print(f"app_data is: {app_data}")
    print(f"user_data is: {user_data}")
    save_config(str(sender), str(app_data))


def clb_selectable(sender, app_data, user_data):
    print(f"Row {user_data}")
    dpg.set_value("target_name", user_data)
    save_config("target_name",user_data)

def bin_callback(sender, app_data):
    print('OK was clicked.')
    print("Sender: ", sender)
    print("App Data: ", app_data)
    dpg.set_value("bin_path", app_data['file_path_name'])
    save_config("bin_path", app_data['file_path_name'])


def rtt_connect_callback(sender, app_data):
    print('OK was clicked.')
    print("Sender: ", sender)
    print("App Data: ", app_data)
    rttThread.Connect()

def rtt_disconnect_callback(sender, app_data):
    print('OK was clicked.')
    print("Sender: ", sender)
    print("App Data: ", app_data)
    rttThread.DisConnect()
def rtt_clear_callback(sender, app_data):
    print('OK was clicked.')
    print("Sender: ", sender)
    print("App Data: ", app_data)
    dpg.set_value("rtt_log", "")

def list_devices_callback(sender, app_data, user_data):
    print('OK was clicked.')
    print("Sender: ", sender)
    print("App Data: ", app_data)
    print("User Data: ", user_data)
    allProbes = ConnectHelper.get_all_connected_probes(blocking=False)
    list = []  
    if len(allProbes):
        #ConnectHelper._print_probe_list(allProbes)
        for index, probe in enumerate(allProbes):
            board_info = probe.associated_board_info
            list.append(probe.description) 
            print("probe.description",probe.description)
        dpg.configure_item('links',items=list,default_value=list[0])
    else:
        print(colorama.Fore.RED + "No available debug probes are connected" + colorama.Style.RESET_ALL)
    print(list)
    



def list_devices():
    print('list_devices was clicked.')
    allProbes = ConnectHelper.get_all_connected_probes(blocking=False)
    list = []  
    if len(allProbes):
        #ConnectHelper._print_probe_list(allProbes)
        for index, probe in enumerate(allProbes):
            board_info = probe.associated_board_info
            list.append(probe.description) 
            print("probe.description",probe.description)
    else:
        print(colorama.Fore.RED + "No available debug probes are connected" + colorama.Style.RESET_ALL)
    print(list)
    return list

def erase_callback(sender, app_data):
    print('OK was clicked.')
    print("Sender: ", sender)
    print("App Data: ", app_data)
    pack_path = dpg.get_value("pack_path");
    print("pack_path\n")
    if len(pack_path)==0 :
        pack_path = None
    target_name = dpg.get_value("target_name");
    if len(target_name)==0 :
        target_name = None
    session = ConnectHelper.session_with_chosen_probe(
                        project_dir=None,
                        config_file=None,
                        user_script=None,
                        no_config=None,
                        pack=pack_path, 
                        unique_id=None,
                        blocking=(not None),
                        connect_mode=None,
                        options = {"frequency": 4000000, "target_override": target_name},
                        option_defaults=None,
                        )
    if session is None:
        LOG.error("No device available to erase")
        return 1
    with session:
        #mode = self._args.erase_mode or FlashEraser.Mode.SECTOR
        eraser = FlashEraser(session, FlashEraser.Mode.CHIP)

        #addresses = flatten_args(self._args.addresses)
        eraser.erase(None)
    dpg.set_value("flash_progress_bar", 1)


def load_callback(sender, app_data):
    print('OK was clicked.')
    print("Sender: ", sender)
    print("App Data: ", app_data)
    pack_path = dpg.get_value("pack_path");
    print(pack_path)
    if len(pack_path)==0 :
        pack_path = None
    target_name = dpg.get_value("target_name");
    if len(target_name)==0 :
        target_name = None
    print(target_name)
    session = ConnectHelper.session_with_chosen_probe(
                        project_dir=None,
                        config_file=None,
                        user_script=None,
                        no_config=None,
                        pack=pack_path, 
                        unique_id=None,
                        blocking=(not None),
                        connect_mode=None,
                        options = {"frequency": 4000000, "target_override": target_name},
                        option_defaults=None,
                        )
    with session:
        programmer = FileProgrammer(session,progress=print_progress,
                        chip_erase=None,
                        no_reset=None)
        filename = dpg.get_value("bin_path");
        if len(filename)==0 :
            print('Bin path is NULL.')
            return
        # Get an initial path with the argument as-is.
        file_path = Path(filename).expanduser()

        # Look for a base address suffix. If the supplied argument including an address suffix
        # references an existing file, then the address suffix is not extracted.
        base_address = None

        # Resolve our path.
        file_path = Path(filename).expanduser().resolve()
        filename = str(file_path)

        if base_address is None:
            LOG.info("Loading %s", filename)
        else:
            LOG.info("Loading %s at %#010x", filename, base_address)

        programmer.program(filename,
                        base_address=0x8000000,
                        file_format=None)

def pack_cancel_callback(sender, app_data):
    print('Cancel was clicked.')
    print("Sender: ", sender)
    print("App Data: ", app_data)

def start_ui():
    dpg.add_texture_registry(label="Demo Texture Container", tag="__demo_texture_container")
    dpg.add_colormap_registry(label="Demo Colormap Registry", tag="__demo_colormap_registry")

    with dpg.theme(tag="__demo_hyperlinkTheme"):
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button, [0, 0, 0, 0])
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, [0, 0, 0, 0])
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, [29, 151, 236, 25])
            dpg.add_theme_color(dpg.mvThemeCol_Text, [29, 151, 236])

    with dpg.window(tag="Primary Window",label="PyOcdTools", width=window_width-20, height=window_height, on_close=_on_demo_close, pos=(0, 0),collapsed=False):
        with dpg.menu_bar():

            with dpg.menu(label="关于"):
                with dpg.group(horizontal=False):
                    dpg.add_menu_item(label="版本:V0.1.0")
        with dpg.collapsing_header(label="Links", default_open=True):
            with dpg.group(horizontal=True):
                if len(list_devices()):
                    dpg.add_combo( tag="links",items=list_devices(),default_value=list_devices()[0])
                else:
                    dpg.add_combo( tag="links",default_value="No device found.")
                dpg.add_button(tag="list_devices",label="刷新",user_data=dpg.last_container(), callback=list_devices_callback)

        with dpg.collapsing_header(label="Pack 设置", default_open=False):
            with dpg.child_window(autosize_x=True, height=50):
                
                with dpg.group(horizontal=True):
                    dpg.add_input_text(  multiline=False, tracked=True,callback=intput_callback, 
                                       track_offset=1, width=400, height=0,tag="pack_path",default_value=read_config("pack_path"))

                    with dpg.file_dialog(label="选择Pack", width=600, height=400, show=False,  callback=pack_callback, 
                                         tag="file_dialog_id",cancel_callback=pack_cancel_callback,default_path="D:\\work\MCU\\software\\"):
                        dpg.add_file_extension(".pack", color=(255, 255, 255, 255))
                    dpg.add_button(label="选择Pack",user_data=dpg.last_container(), callback=lambda s, a, u: dpg.configure_item(u, show=True))
            with dpg.child_window(autosize_x=True, height=400):
                dpg.add_button(label="显示Target", callback=show_target)
                with dpg.table(tag="pack_table",header_row=True, policy=dpg.mvTable_SizingFixedFit, row_background=True, reorderable=True, 
                            resizable=True, no_host_extendX=False, hideable=True, 
                            borders_innerV=True, delay_search=True, borders_outerV=True, borders_innerH=True, borders_outerH=True,width=1400,height=600):

                    dpg.add_table_column(label="Name", width_stretch=True, init_width_or_weight=0.0)
                    dpg.add_table_column(label="Vendor", width_stretch=True, init_width_or_weight=0.0)
                    dpg.add_table_column(label="Part Number", width_stretch=True, init_width_or_weight=0.0)
                    dpg.add_table_column(label="Families",width_stretch=True, init_width_or_weight=0.0)
                    dpg.add_table_column(label="Source", width_stretch=True, init_width_or_weight=0.0)


        with dpg.collapsing_header(label="固件烧录", default_open=True):
            with dpg.child_window(autosize_x=True, height=170):
                with dpg.group(horizontal=True):
                    dpg.add_input_text(  multiline=False, tracked=True,callback=intput_callback, track_offset=1, width=400, height=0,tag="target_name",default_value=read_config("target_name"))
                    dpg.add_button(label="选择Target")
                with dpg.group(horizontal=True):
                    dpg.add_input_text(  multiline=False, readonly=True, tracked=True, track_offset=1, width=400, height=0,tag="bin_path",default_value=read_config("bin_path"))
                    with dpg.file_dialog(label="选择固件", width=600, height=400, show=False,  callback=bin_callback, tag="bin_file_dialog_id",cancel_callback=pack_cancel_callback,default_path="D:\\work\MCU\\software\\"):
                        dpg.add_file_extension(".bin", color=(255, 255, 255, 255))
                        dpg.add_file_extension(".*", color=(255, 255, 255, 255))
                    dpg.add_button(label="选择固件",user_data=dpg.last_container(), callback=lambda s, a, u: dpg.configure_item(u, show=True))
                with dpg.group(horizontal=True):
                    dpg.add_button(label="擦除固件",callback=   erase_callback)
                    dpg.add_button(label="烧录固件",callback=   load_callback)
                with dpg.group(horizontal=True):
                    dpg.add_progress_bar(label="Progress Bar", default_value=0.0, width=400, height=0, tag="flash_progress_bar")

        with dpg.collapsing_header(label="RTT Viewer", default_open=True):
            with dpg.child_window(autosize_x=True, height=370):
                with dpg.group(horizontal=True):
                    dpg.add_button(tag="rtt_connect",label="连接",callback=   rtt_connect_callback)
                    dpg.add_button(tag="rtt_disconnect",label="断开连接",callback=   rtt_disconnect_callback)
                    dpg.add_button(tag="rtt_clear",label="清除日志",callback=   rtt_clear_callback)
                dpg.add_input_text(tag="rtt_log",  multiline=True, readonly=True, width=-1, height=-1)
        #print(os.getcwd())
def show_ui():
    filename = resource_path(os.path.join("res","NotoSerifCJKjp-Medium.otf"))
    UsePlatform()
    dpg.create_context()
    dpg.create_viewport(title='PyOcdTools', width=window_width, height=window_height)
    with dpg.font_registry():
        with dpg.font(filename, 26, tag="custom font"):
            dpg.add_font_range_hint(dpg.mvFontRangeHint_Chinese_Simplified_Common)
        dpg.bind_font(dpg.last_container())
    dpg.set_global_font_scale(1.0)
    ctypes.windll.shcore.SetProcessDpiAwareness(2)

    start_ui()
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.start_dearpygui()
    dpg.destroy_context()

if __name__ == '__main__':
    print("当前版本： ", __version__)
    print_devices()
    #print_pack_targets()
    #print_targets()
    #erase_targets()
    #load_targets()
    rttThread = RTTThread()
    show_ui()
    #open_rtt()
    #progress_print(fun=del_progress)


 #pyocd rtt --pack D:\MCU\software\Nationstech.N32G45x_DFP.1.0.1.pack  --target n32g455rcl7

 #pyocd load --pack D:\MCU\software\Nationstech.N32G45x_DFP.1.0.1.pack  --target n32g455rcl7 -a 0x8000000  D:\MCU\lt9211-bba-box_vscode\Project\TargetFile\Target.bin

 #pyocd list --target --pack  D:\work\MCU\software\Nationstech.N32G45x_DFP.1.0.1.pack

 #pyocd erase  --pack D:\work\MCU\software\Nationstech.N32G45x_DFP.1.0.1.pack --target n32g455rcl7 --chip -f 10000k