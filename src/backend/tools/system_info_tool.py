import platform
import subprocess
import shutil
import psutil


def _gpu_info() -> list[dict]:
    """
    Try multiple strategies to gather GPU info, best-effort.
    Returns a list of dicts with whatever fields are available.
    """
    gpus = []

    # Strategy 1: nvidia-smi (NVIDIA)
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=name,driver_version,memory.total,utilization.gpu,temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                timeout=5,
                text=True,
                stderr=subprocess.DEVNULL,
            )
            for line in out.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 5:
                    gpus.append({
                        "name": parts[0],
                        "driver": parts[1],
                        "vram_mb": int(parts[2]) if parts[2].isdigit() else parts[2],
                        "utilization_pct": int(parts[3]) if parts[3].isdigit() else parts[3],
                        "temp_c": int(parts[4]) if parts[4].isdigit() else parts[4],
                        "source": "nvidia-smi",
                    })
        except Exception:
            pass

    # Strategy 2: rocm-smi (AMD)
    if not gpus and shutil.which("rocm-smi"):
        try:
            out = subprocess.check_output(
                ["rocm-smi", "--showproductname", "--showuse", "--showmeminfo", "vram", "--json"],
                timeout=5,
                text=True,
                stderr=subprocess.DEVNULL,
            )
            import json
            data = json.loads(out)
            for card_id, info in data.items():
                if card_id == "system":
                    continue
                gpus.append({
                    "name": info.get("Card series", info.get("Card model", card_id)),
                    "utilization_pct": info.get("GPU use (%)"),
                    "vram_used_mb": info.get("VRAM Total Used Memory (B)"),
                    "vram_total_mb": info.get("VRAM Total Memory (B)"),
                    "source": "rocm-smi",
                })
        except Exception:
            pass

    # Strategy 3: lspci fallback (name only, no metrics)
    if not gpus and shutil.which("lspci"):
        try:
            out = subprocess.check_output(
                ["lspci"],
                timeout=5,
                text=True,
                stderr=subprocess.DEVNULL,
            )
            for line in out.splitlines():
                if any(k in line.lower() for k in ("vga", "3d controller", "display controller")):
                    name = line.split(":", 2)[-1].strip()
                    gpus.append({"name": name, "source": "lspci"})
        except Exception:
            pass

    return gpus


def _laptop_model() -> str | None:
    """Try to identify the laptop/system model via DMI data (Linux) or system_profiler (macOS)."""
    system = platform.system()
    if system == "Linux":
        for path in (
            "/sys/class/dmi/id/product_name",
            "/sys/class/dmi/id/sys_vendor",
        ):
            try:
                val = open(path).read().strip()
                if val and val not in ("To Be Filled By O.E.M.", "Default string", ""):
                    return val
            except Exception:
                pass
    elif system == "Darwin":
        try:
            out = subprocess.check_output(
                ["system_profiler", "SPHardwareDataType"],
                timeout=5, text=True, stderr=subprocess.DEVNULL,
            )
            for line in out.splitlines():
                if "Model Name" in line or "Model Identifier" in line:
                    return line.split(":", 1)[-1].strip()
        except Exception:
            pass
    return None


def get_system_info() -> dict:
    """
    Returns a snapshot of the host machine's hardware and OS state.
    Fields: os, architecture, hostname, cpu (model, physical_cores, logical_cores,
    freq_mhz, usage_pct_per_core, usage_pct_total), memory (total_gb, available_gb,
    used_gb, percent), swap (total_gb, used_gb, percent), gpu (list), model (str|None).
    """
    uname = platform.uname()
    cpu_freq = psutil.cpu_freq()
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()

    # Per-core usage — short interval to avoid blocking too long
    per_core = psutil.cpu_percent(interval=0.5, percpu=True)

    return {
        "os": f"{uname.system} {uname.release}",
        "architecture": uname.machine,
        "hostname": uname.node,
        "model": _laptop_model(),
        "cpu": {
            "brand": platform.processor() or uname.processor or "Unknown",
            "physical_cores": psutil.cpu_count(logical=False),
            "logical_cores": psutil.cpu_count(logical=True),
            "freq_mhz": round(cpu_freq.current, 1) if cpu_freq else None,
            "freq_max_mhz": round(cpu_freq.max, 1) if cpu_freq else None,
            "usage_pct_total": psutil.cpu_percent(interval=None),
            "usage_pct_per_core": per_core,
        },
        "memory": {
            "total_gb": round(mem.total / 1e9, 2),
            "available_gb": round(mem.available / 1e9, 2),
            "used_gb": round(mem.used / 1e9, 2),
            "percent": mem.percent,
        },
        "swap": {
            "total_gb": round(swap.total / 1e9, 2),
            "used_gb": round(swap.used / 1e9, 2),
            "percent": swap.percent,
        },
        "gpu": _gpu_info(),
    }
