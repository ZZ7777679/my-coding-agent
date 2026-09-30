"""仅供在线资源测试的公开 HTTP 替身。

Public HTTP substitute used only in skill tests.
"""

import asyncio
import io
import zipfile

import httpx

BODY = (
    "---\nname: sample-skill\ndescription: Small reusable method\n---\nRead references/note.md.\n"
)


def archive_bytes(*, escape=False):
    """生成含文本与二进制资源的仓库样本。

    Build a repository with text and binary assets.
    """
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.comment = b"1" * 40
        archive.writestr("repo-HEAD/skills/demo/SKILL.md", BODY)
        archive.writestr("repo-HEAD/skills/demo/references/note.md", "Keep this reference.\n")
        archive.writestr("repo-HEAD/skills/demo/assets/pixel.bin", b"\x00\xff\x80")
        archive.writestr("repo-HEAD/skills/second/SKILL.md", BODY.replace("sample-skill", "second"))
        if escape:
            archive.writestr("repo-HEAD/skills/demo/../../../../escaped.txt", "must not escape")
    return output.getvalue()


async def catalog_response(request):
    """让桌面走真实下载 / 解析 / 写入，仅替换外部 HTTP。

    Replace external HTTP, keeping the real import path.
    """
    assert "authorization" not in request.headers and "x-opencode-session" not in request.headers
    if request.url.host == "skills.sh":
        if request.url.params.get("q") == "slow":
            await asyncio.Event().wait()
        return httpx.Response(
            200,
            json={
                "skills": [
                    {
                        "id": "fixture/repo/sample-skill",
                        "name": "sample-skill",
                        "source": "fixture/repo",
                        "installs": 3,
                    }
                ]
            },
        )
    if request.url.host == "codeload.github.com":
        return httpx.Response(200, content=archive_bytes())
    raise AssertionError(f"Unexpected test source: {request.url.host}")
