"""Verifica cache, downloads interrompidos e inspeção sem rede externa."""

import json
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest
import requests

from apuracao import download as module


class Response:
    """Representa uma resposta de rede controlada pelo teste."""

    headers: dict[str, str] = {}

    def __init__(self, chunks: list[bytes], interrupt: bool = False) -> None:
        """Configura os blocos que serão recebidos."""
        self.chunks = chunks
        self.interrupt = interrupt

    def __enter__(self) -> "Response":
        """Abre o contexto da resposta."""
        return self

    def __exit__(self, *args: object) -> None:
        """Fecha o contexto da resposta."""

    def raise_for_status(self) -> None:
        """Representa uma resposta HTTP de sucesso."""

    def iter_content(self, chunk_size: int) -> Iterator[bytes]:
        """Entrega blocos e opcionalmente simula uma conexão interrompida."""
        yield from self.chunks
        if self.interrupt:
            raise requests.ConnectionError("interrompido")


class Client:
    """Substitui a sessão HTTP sem acesso à rede."""

    def __init__(self, response: Response) -> None:
        """Configura a resposta esperada."""
        self.response = response

    def __enter__(self) -> "Client":
        """Abre a sessão de teste."""
        return self

    def __exit__(self, *args: object) -> None:
        """Fecha a sessão de teste."""

    def get(self, *args: object, **kwargs: object) -> Response:
        """Retorna a resposta controlada."""
        return self.response


def test_cache_never_requests_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Preserva o arquivo existente sem iniciar uma nova requisição."""
    target = tmp_path / "cache.json"
    target.write_text('[{"valor": 1}]', encoding="utf-8")
    monkeypatch.setattr(module, "session", lambda: pytest.fail("Cache acessou a rede"))
    assert module.download("https://example.invalid", target, json_response=True) == target


@pytest.mark.parametrize("interrupt", [False, True])
def test_stream_publication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interrupt: bool) -> None:
    """Publica somente arquivos completos e limpa o parcial após falha."""
    target = tmp_path / "subdir" / "bu.zip"
    monkeypatch.setattr(module, "session", lambda: Client(Response([b"abc", b"def"], interrupt)))
    if interrupt:
        with pytest.raises(requests.ConnectionError):
            module.download("https://example.invalid", target)
        assert not target.exists()
    else:
        module.download("https://example.invalid", target)
        assert target.read_bytes() == b"abcdef"
    assert not target.with_name("bu.zip.part").exists()


def test_http_200_html_is_not_cached_as_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Recusa páginas de bloqueio mesmo quando o status HTTP indica sucesso."""
    target = tmp_path / "resposta.json"
    monkeypatch.setattr(module, "session", lambda: Client(Response([b"<html>Request Rejected</html>"])))
    with pytest.raises(json.JSONDecodeError):
        module.download("https://example.invalid", target, json_response=True)
    assert not target.exists()


def test_latin1_sample_preserves_real_header(tmp_path: Path) -> None:
    """Preserva espaços do cabeçalho e acentos sem ler todo o CSV."""
    target = tmp_path / "bu.zip"
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("bu.csv", '"SG_ UF";"NM_MUNICIPIO"\n"SP";"São Paulo"\n"RJ";"Rio"\n'.encode("latin-1"))
    result = module.inspect_zip(target, rows=1)[0]
    assert result["colunas"] == ["SG_ UF", "NM_MUNICIPIO"]
    assert result["amostra"] == [{"SG_ UF": "SP", "NM_MUNICIPIO": "São Paulo"}]


def test_missing_uf_does_not_silently_choose_first_round() -> None:
    """Recusa cobertura incompleta no segundo turno publicado."""
    metadata = {"resources": [{"url": "https://cdn.tse.jus.br/bweb_2t_AC_123.zip.sha512"}]}
    with pytest.raises(ValueError, match="incompleto"):
        module.discover_resources(metadata)


def test_discovery_uses_official_checksum_link_for_omitted_zip() -> None:
    """Resolve ZIP omitido da lista quando o hash oficial publica seu caminho."""
    metadata = {"resources": [{"url": f"https://cdn.tse.jus.br/bweb_2t_{uf}_123.zip.sha512"}
                              for uf in module.UFS]}
    turn, resources = module.discover_resources(metadata)
    assert turn == 2
    assert len(resources) == 28
    assert all(row["url"] + ".sha512" == row["checksum_url"] for row in resources)
