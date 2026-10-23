"""SSH/SFTP relay; numerical execution always uses a node's local disk."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import hashlib
from typing import Any

from .protocol import Node, publish_json, read_json, safe_id


def powershell_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


class Transport:
    """Idempotent small-message delivery with bounded SSH calls and pinned host keys."""
    def __init__(self, node: Node):
        self.node = node

    def remote(self, arguments: list[str], *, timeout: float = 30.) -> Any:
        n = self.node
        command = ("$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; "
            "[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false); "
            f"Set-Location -LiteralPath {powershell_literal(n.repository)}; "
            f"& {powershell_literal(n.python)} -u run_workflow_6_fleet.py "
            + " ".join(powershell_literal(v) for v in arguments) + "; exit $LASTEXITCODE")
        encoded = base64.b64encode(command.encode("utf-16le")).decode()
        result = subprocess.run(["ssh.exe", "-F", n.ssh_config, "-o", "ConnectTimeout=5",
            n.ssh_host, "powershell.exe -NoProfile -NonInteractive -EncodedCommand " + encoded],
            capture_output=True, timeout=timeout)
        if result.returncode:
            raise ConnectionError(result.stderr.decode("utf-8", errors="replace")[-1500:])
        return json.loads(result.stdout.decode("utf-8-sig"))

    def inspect(self) -> dict[str, Any]:
        if self.node.ssh_host:
            return self.remote(["inspect", "--root", self.node.root])
        from .worker import worker_snapshot
        return worker_snapshot(Path(self.node.root))

    def publish(self, relative: str, data: Any) -> None:
        """Only protocol-relative JSON files; no arbitrary remote shell fragments."""
        validate_relative(relative)
        if self.node.ssh_host:
            payload=json.dumps(data,allow_nan=False).encode('utf-8')
            sha=hashlib.sha256(payload).hexdigest()
            with tempfile.TemporaryDirectory(prefix='wf6_message_') as folder:
                path=Path(folder)/'message.json';path.write_bytes(payload)
                remote=self.node.root.replace('\\','/').rstrip('/')+'/uploads/'+sha+'.json'
                if any('"' in v or '\n' in v for v in (remote,str(path))):raise ValueError('Unsafe upload path')
                batch=f'put "{path.as_posix()}" "{remote}"\nbye\n'
                result=subprocess.run(['sftp.exe','-F',self.node.ssh_config,'-o','ConnectTimeout=5','-b','-',self.node.ssh_host],
                    input=batch.encode(),capture_output=True,timeout=30.)
                if result.returncode:raise ConnectionError(result.stderr.decode('utf-8',errors='replace')[-1000:])
            self.remote(['publish-file','--root',self.node.root,'--relative',relative,'--sha256',sha])
        else:
            publish_json(Path(self.node.root) / relative, data)

    def fetch(self, relative: str, destination: Path) -> None:
        validate_relative(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".download")
        if not self.node.ssh_host:
            shutil.copy2(Path(self.node.root) / relative, temporary)
        else:
            remote = self.node.root.replace("\\", "/").rstrip("/") + "/" + relative
            if any('"' in s or "\n" in s for s in (remote, str(temporary))):
                raise ValueError("Unsupported SFTP path")
            batch = f'get "{remote}" "{temporary.as_posix()}"\nbye\n'
            result = subprocess.run(["sftp.exe", "-F", self.node.ssh_config,
                "-o", "ConnectTimeout=5", "-b", "-", self.node.ssh_host], input=batch.encode(),
                capture_output=True, timeout=180.)
            if result.returncode:
                raise ConnectionError(result.stderr.decode("utf-8", errors="replace")[-1000:])
        os.replace(temporary, destination)

    def stop_when_idle(self) -> None:
        self.publish("STOP", {"reason": "Coordinator stopped dispatch; finish current task only"})


def validate_relative(relative: str) -> str:
    if not relative or any(x in relative for x in ("\\", ":", '"', "\n", "\r")) or relative.startswith("/") or any(p in ("", ".", "..") for p in relative.split("/")):
        raise ValueError("Unsafe protocol relative path")
    return relative
