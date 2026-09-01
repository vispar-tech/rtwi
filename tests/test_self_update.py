from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Self

from rtwi import self_update


def test_version_tuple_major_minor_patch() -> None:
    assert self_update._version_tuple("v1.2.3") == (1, 2, 3)


def test_version_tuple_no_v_prefix() -> None:
    assert self_update._version_tuple("0.1.0") == (0, 1, 0)


def test_version_tuple_two_parts() -> None:
    assert self_update._version_tuple("v2.5") == (2, 5)


def test_version_tuple_non_numeric_stops() -> None:
    assert self_update._version_tuple("v1.2.3beta") == (1, 2)


def test_bin_dir() -> None:
    d = self_update._bin_dir()
    assert d.is_dir()


class FakeHTTPClient:
    """Minimal httpx-like client for testing self_update."""

    def __init__(self, tag: str = "v1.0.0") -> None:
        self._tag = tag
        self._requests: list[str] = []

    def get(self, url: str, **kwargs: object) -> SimpleNamespace:
        self._requests.append(url)
        if "releases/latest" in url:
            return SimpleNamespace(
                json=lambda: {"tag_name": self._tag},
                raise_for_status=lambda: None,
            )
        return SimpleNamespace(
            raise_for_status=lambda: None,
            headers={"content-length": "100"},
        )

    def stream(self, method: str, url: str, **kwargs: object) -> object:
        self._requests.append(url)

        class CM:
            def __enter__(self) -> Self:
                return self

            def __exit__(self, *_a: object) -> None:
                pass

            @property
            def headers(self) -> dict[str, str]:
                return {"content-length": "100"}

            def raise_for_status(self) -> None:
                pass

            def iter_bytes(self, chunk_size: int = 65536) -> list[bytes]:
                return [b"\x00" * 10]

        return CM()

    def close(self) -> None:
        pass


def test_check_for_update_up_to_date() -> None:
    client = FakeHTTPClient(tag="v0.0.0")
    result = self_update.check_for_update(client)
    assert result.updated is False
    assert "up to date" in result.message


def test_check_for_update_available() -> None:
    client = FakeHTTPClient(tag="v99.0.0")
    result = self_update.check_for_update(client)
    assert result.updated is False
    assert "update available" in result.message


def test_check_for_update_network_error() -> None:
    class ErrClient:
        def get(self, url: str, **kwargs: object) -> None:
            raise ConnectionError("no network")

        def close(self) -> None:
            pass

    result = self_update.check_for_update(ErrClient())
    assert result.updated is False
    assert "failed" in result.message


def test_perform_update_already_up_to_date() -> None:
    client = FakeHTTPClient(tag="v0.0.0")
    result = self_update.perform_update(client)
    assert result.updated is False
    assert "up to date" in result.message


def test_install_extracted_missing_launcher(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    dest = tmp_path / "dest"
    dest.mkdir()
    err = self_update._install_extracted(src, dest, "1.0.0")
    assert err == "downloaded archive did not contain an rtwi binary"


def test_install_extracted_success(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "rtwi").write_text("#!/bin/sh\necho ok")
    (src / "rtwi").chmod(0o755)
    internal = src / "_internal"
    internal.mkdir()
    (internal / "lib.txt").write_text("data")

    dest = tmp_path / "dest"
    dest.mkdir()

    err = self_update._install_extracted(src, dest, "1.0.0")
    assert err is None
    assert (dest / "rtwi").exists()
    assert (dest / "_internal" / "lib.txt").exists()
