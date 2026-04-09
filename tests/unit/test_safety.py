import pytest

from agent.infra.safety import SafetyViolation, check_step


def test_block_rm_rf_root():
    with pytest.raises(SafetyViolation):
        check_step("shell_runner", {"command": "rm -rf /"})


def test_block_rm_rf_dot():
    with pytest.raises(SafetyViolation):
        check_step("shell_runner", {"command": "rm -rf ."})


def test_block_rm_rf_home():
    with pytest.raises(SafetyViolation):
        check_step("shell_runner", {"command": "rm -rf ~"})


def test_block_fork_bomb():
    with pytest.raises(SafetyViolation):
        check_step("shell_runner", {"command": ":(){ :|:& };:"})


def test_block_dd_disk():
    with pytest.raises(SafetyViolation):
        check_step("shell_runner", {"command": "dd if=/dev/zero of=/dev/sda"})


def test_allow_safe_rm():
    check_step("shell_runner", {"command": "rm /tmp/foo.txt"})


def test_allow_normal_command():
    check_step("shell_runner", {"command": "ls -la /tmp"})


def test_block_dangerous_path_in_file_ops():
    with pytest.raises(SafetyViolation):
        check_step("file_ops", {"action": "write", "path": "/etc/passwd", "content": "x"})


def test_allow_tmp_path():
    check_step("file_ops", {"action": "write", "path": "/tmp/foo.txt", "content": "x"})
