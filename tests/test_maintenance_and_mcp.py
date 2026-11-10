import asyncio
import json
import sys
import time

import pytest
from mcp import Client, StdioServerParameters

from harnesslab.sandbox import Result
from scripts.reconcile import reconcile


def test_reconciliation_retains_unknown_and_active_jobs():
    identities=["a"*12,"b"*12,"c"*12]
    jobs={"1"*32:{"status":"solved"},"2"*32:{"status":"running"}}
    calls=[]
    class Store:
        def get(self,identity):return jobs.get(identity)
    def command(argv,**kwargs):
        calls.append(argv)
        if argv[1]=="ps":return Result(0,"\n".join(identities))
        if argv[1]=="inspect":
            run_id=str(identities.index(argv[2])+1)*32
            return Result(0,json.dumps([{"Config":{"Labels":{"harnesslab.managed":"true","harnesslab.run":run_id}}}]))
        return Result(0,"")
    dry=reconcile(Store(),command=command)
    assert [r["action"] for r in dry]==["eligible","retain_unknown_or_active","retain_unknown_or_active"]
    assert not any(c[1]=="rm" for c in calls)
    applied=reconcile(Store(),apply=True,command=command)
    assert applied[0]["action"]=="removed"
    assert [c for c in calls if c[1]=="rm"]==[["docker","rm","-f","a"*12]]


def test_crashed_stdio_server_fails_without_hanging():
    code="from mcp.server import MCPServer\nimport os\ns=MCPServer('crash-fixture')\n@s.tool()\ndef crash() -> str:\n os._exit(73)\ns.run()"
    async def check():
        async with Client(StdioServerParameters(command=sys.executable,args=["-c",code]),read_timeout_seconds=1) as client:
            assert [t.name for t in (await client.list_tools()).tools]==["crash"]
            await asyncio.wait_for(client.call_tool("crash",{}),timeout=3)
    started=time.monotonic()
    with pytest.raises(ExceptionGroup):
        asyncio.run(check())
    assert time.monotonic()-started<5


def test_unresponsive_stdio_server_has_bounded_handshake():
    async def check():
        async with Client(StdioServerParameters(command=sys.executable,args=["-c","import time;time.sleep(30)"]),read_timeout_seconds=.1):
            pass
    started=time.monotonic()
    with pytest.raises((ExceptionGroup,TimeoutError)):
        asyncio.run(asyncio.wait_for(check(),timeout=2))
    assert time.monotonic()-started<5
