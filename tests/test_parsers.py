"""Tests for the parsers behind the ported features.

Every one of these takes the text a Windows program printed and returns a
value, so they run anywhere — which matters, because the machine this package
is developed on cannot run a single one of the commands whose output they
parse. The samples below are the shapes those programs actually emit,
localised ones included.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from wslx import config, info, mount, network, run, scheduler, usb, wslconf
from wslx.wsl import WslError


def test_decode_falls_back_to_the_console_code_page() -> None:
    """netsh on a Spanish Windows is not UTF-8, and must not raise."""
    assert "conexi" in run.decode("conexión\n".encode("cp850")).lower()


def test_result_message_prefers_stderr_but_takes_stdout() -> None:
    """`wsl.exe` reports failures on stdout as often as on stderr."""
    assert run.Result(1, "the distribution does not exist\nusage: ...", "").message == (
        "the distribution does not exist"
    )
    assert run.Result(1, "", "access denied").message == "access denied"
    assert run.Result(3, "", "").message == "exit code 3"


def test_parse_df_reads_the_last_row_not_the_header() -> None:
    output = (
        "Filesystem     1B-blocks       Used  Available Use% Mounted on\n"
        "/dev/sdc    1081101176832 3221225472 1023410536448   1% /\n"
    )
    usage = info.parse_df(output)
    assert usage is not None
    assert usage.used == 3221225472
    assert usage.percent == 0 or usage.percent == 1


def test_parse_df_survives_a_translated_header() -> None:
    output = (
        "S.ficheros    bloques de 1B     Usados Disponibles Uso% Montado en\n"
        "/dev/sdc      1000000000    500000000   500000000  50% /\n"
    )
    usage = info.parse_df(output)
    assert usage is not None and usage.percent == 50


def test_parse_os_release_takes_pretty_name() -> None:
    output = 'NAME="Ubuntu"\nPRETTY_NAME="Ubuntu 24.04.1 LTS"\nVERSION_ID="24.04"\n'
    assert info.parse_os_release(output) == "Ubuntu 24.04.1 LTS"


def test_parse_addresses_drops_loopback_and_keeps_order() -> None:
    output = (
        "1: lo: <LOOPBACK,UP> mtu 65536\n"
        "    inet 127.0.0.1/8 scope host lo\n"
        "2: eth0: <BROADCAST,MULTICAST,UP> mtu 1500\n"
        "    inet 172.20.153.42/20 brd 172.20.159.255 scope global eth0\n"
    )
    assert info.parse_addresses(output) == ["172.20.153.42"]


def test_human_uses_the_unit_a_person_would() -> None:
    assert info.human(1536) == "2 KB"
    assert info.human(3 * 1024**3) == "3.00 GB"


def test_parse_forwards_reads_the_netsh_table() -> None:
    output = (
        "Escuchar en ipv4:             Conectar a ipv4:\n"
        "\n"
        "Dirección       Puerto      Dirección       Puerto\n"
        "--------------- ----------  --------------- ----------\n"
        "0.0.0.0         8080        172.20.153.42   80\n"
        "127.0.0.1       5432        172.20.153.42   5432\n"
    )
    rules = network.parse_forwards(output)
    assert [rule.listen_port for rule in rules] == [8080, 5432]
    assert rules[0].connect_address == "172.20.153.42"
    assert str(rules[0]) == "0.0.0.0:8080 -> 172.20.153.42:80"


def test_parse_forwards_ignores_the_dashed_rule_and_headings() -> None:
    assert network.parse_forwards("Address Port Address Port\n---- ---- ---- ----\n") == []


@pytest.mark.parametrize("bad", ["0", "65536", "-1"])
def test_port_rejects_what_is_not_a_port(bad: str) -> None:
    with pytest.raises(WslError):
        network.port(bad)


def test_address_rejects_a_name() -> None:
    with pytest.raises(WslError):
        network.address("localhost")


def test_firewall_rule_is_named_after_the_port_so_it_can_be_found_again() -> None:
    assert network.Forward(8080, "172.20.0.2", 80).rule == "wslx 8080"


def test_parse_state_reads_usbipd_json() -> None:
    payload = """
    {"Devices": [
      {"BusId": "2-3", "Description": "USB Serial Device (COM3)",
       "HardwareId": "1a86:7523", "PersistedGuid": "9f1a...", "ClientIPAddress": "172.20.0.2"},
      {"BusId": "2-4", "Description": "Webcam", "HardwareId": "046d:0825"},
      {"BusId": null, "Description": "Unplugged, still shared", "PersistedGuid": "aaaa"}
    ]}
    """
    devices = usb.parse_state(payload)
    assert [device.busid for device in devices] == ["2-3", "2-4"]
    assert devices[0].attached and devices[0].shared and devices[0].state == "Attached"
    assert not devices[1].shared and devices[1].state == "Not shared"


def test_parse_state_on_something_that_is_not_json() -> None:
    assert usb.parse_state("usbipd: unknown command") == []


def test_parse_list_reads_the_text_table() -> None:
    output = (
        "Connected:\n"
        "BUSID  VID:PID    DEVICE                                        STATE\n"
        "2-3    1a86:7523  USB Serial Device (COM3)                      Not shared\n"
        "2-4    046d:0825  HD Webcam C270                                Attached\n"
        "\n"
        "Persisted:\n"
    )
    devices = usb.parse_list(output)
    assert [device.busid for device in devices] == ["2-3", "2-4"]
    assert devices[0].description == "USB Serial Device (COM3)"
    assert devices[1].attached


def test_parse_disks_accepts_the_single_object_powershell_emits() -> None:
    # PowerShell escapes the device path's backslashes on the way into JSON.
    payload = (
        r'{"DeviceID": "\\\\.\\PHYSICALDRIVE0", "Model": "NVMe",'
        r' "Size": 512, "Index": 0}'
    )
    disks = mount.parse_disks(payload, system_index=0)
    assert len(disks) == 1 and disks[0].system


def test_parse_disks_on_no_disks_at_all() -> None:
    assert mount.parse_disks("") == []
    assert mount.parse_disks("null") == []


def test_parse_tasks_keeps_only_the_wslx_folder() -> None:
    output = (
        '"HostName","TaskName","Next Run Time","Status","Logon Mode","Last Run Time",'
        '"Last Result","Author","Task To Run"\n'
        '"PC","\\Microsoft\\Windows\\Defrag","N/A","Ready","x","x","0","x","defrag"\n'
        '"PC","\\wslx\\backup","03/09/2026 22:00:00","Ready","x","x","0","david",'
        '"wsl.exe -d alfa","DAILY"\n'
    )
    tasks = scheduler.parse_tasks(output)
    assert [task.label for task in tasks] == ["backup"]
    assert tasks[0].name == "\\wslx\\backup"


def test_parse_schedule_reads_the_xml_not_the_translated_table() -> None:
    """On a Spanish Windows the CSV says `Diariamente`; the XML says this."""
    xml = (
        '<?xml version="1.0" encoding="UTF-16"?>'
        '<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">'
        "<Triggers><CalendarTrigger><StartBoundary>2026-09-04T09:00:00</StartBoundary>"
        "<ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>"
        "</CalendarTrigger></Triggers></Task>"
    )
    assert scheduler.parse_schedule(xml) == "DAILY"


def test_parse_schedule_knows_the_triggers_that_are_not_calendars() -> None:
    template = (
        '<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">'
        "<Triggers><{tag}/></Triggers></Task>"
    )
    assert scheduler.parse_schedule(template.format(tag="LogonTrigger")) == "ONLOGON"
    assert scheduler.parse_schedule(template.format(tag="BootTrigger")) == "ONSTART"
    assert scheduler.parse_schedule("not xml at all") == ""


@pytest.mark.parametrize("bad", ["one two", "..\\evil", 'quote"'])
def test_label_rejects_anything_task_scheduler_would_read_as_a_path(bad: str) -> None:
    with pytest.raises(WslError):
        scheduler.label(bad)


def test_command_for_quotes_the_distribution_name() -> None:
    """A name is chosen by whoever registered it, not necessarily by us."""
    line = scheduler.command_for("my machine", "apt update")
    assert '"my machine"' in line
    assert line.startswith("wsl.exe -d ")


def test_wslconf_keeps_the_case_wsl_insists_on() -> None:
    parser = wslconf.parse("[wsl2]\nnetworkingMode=mirrored\n")
    assert wslconf.get(parser, "wsl2", "networkingMode") == "mirrored"
    assert "networkingMode" in wslconf.render(parser)


def test_wslconf_put_none_removes_the_key_rather_than_emptying_it() -> None:
    parser = wslconf.parse("[wsl2]\nmemory=8GB\n")
    wslconf.put(parser, "wsl2", "memory", None)
    assert "memory" not in wslconf.render(parser)


def test_proxy_exports_both_spellings_because_half_of_linux_reads_each() -> None:
    proxy = config.Proxy(enabled=True, host="proxy.school", port="8080")
    environment = proxy.environment()
    assert environment["HTTP_PROXY"] == "http://proxy.school:8080"
    assert environment["http_proxy"] == environment["HTTP_PROXY"]


def test_proxy_exports_nothing_when_it_is_off() -> None:
    assert config.Proxy(host="proxy", port="8080").environment() == {}


def test_settings_survive_a_corrupt_file(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """It is a convenience: losing it costs a re-typed proxy, not a crash."""
    monkeypatch.setattr(config, "config_dir", lambda: tmp_path)
    (tmp_path / "settings.json").write_text("{not json", encoding="utf-8")
    assert config.load() == config.Settings()


def test_settings_round_trip(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "config_dir", lambda: tmp_path)
    config.save(config.Settings(proxy=config.Proxy(enabled=True, host="p", port="1")))
    assert config.load().proxy.host == "p"


def test_elevated_script_quotes_a_hostile_distribution_name(tmp_path) -> None:
    """The one string a shell parses has to survive a name with a `&` in it.

    A WSL distribution can be registered by anything the user runs, without
    administrator rights, and its name comes back from `wsl --list`. If that
    name reached an elevated `cmd /c` unquoted, the part after the `&` would
    run as administrator.
    """
    text = run.script_text([["wsl.exe", "--terminate", "a & shutdown /r /t 0"]], tmp_path / "l")
    assert '"a & shutdown /r /t 0"' in text
    # One command, one line — nothing after the quoted name is a second command.
    commands = [line for line in text.splitlines() if line.startswith("wsl.exe")]
    assert len(commands) == 1


def test_elevated_script_keeps_the_commands_in_order_and_logs_each() -> None:
    text = run.script_text([["netsh", "a"], ["netsh", "b"]], Path("C:\\log"))
    lines = [line for line in text.splitlines() if line.startswith("netsh")]
    assert lines == ['netsh a >> "C:\\log" 2>&1', 'netsh b >> "C:\\log" 2>&1']


def test_elevated_script_does_not_force_a_codepage() -> None:
    """diskpart does not survive `chcp 65001`, and the log does not need it."""
    assert "chcp" not in run.script_text([["diskpart", "/s", "x"]], Path("C:\\log"))


def test_command_for_names_the_box_user_only_when_wslx_made_the_machine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`-u box` on someone else's Ubuntu is a task that fails every night."""
    assert " -u box " in scheduler.command_for("alfa", "uptime", user="box")
    assert " -u " not in scheduler.command_for("Ubuntu", "uptime")


def test_result_tail_is_for_programs_that_greet_you_before_failing() -> None:
    """diskpart's first line is its version, so `message` would report that."""
    result = run.Result(1, "Microsoft DiskPart 10.0\n\nThe disk is in use.\n", "")
    assert result.message.startswith("Microsoft DiskPart")
    assert result.tail.endswith("The disk is in use.")


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        (1.0, 1.0),
        (99, config.FONT_SCALE_MAX),
        (0.01, config.FONT_SCALE_MIN),
        ("1.2", 1.2),
        ("huge", 1.0),
        (None, 1.0),
    ],
)
def test_font_scale_cannot_be_stored_into_uselessness(stored, expected) -> None:
    """The settings file is editable, and text too small to read is a trap.

    Zooming is only safe if every way back is reachable — including from a
    value someone typed in by hand.
    """
    assert config.clamp_scale(stored) == expected
