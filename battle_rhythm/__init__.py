"""Battle Rhythm — the Sleeper toolkit, as one package.

Deliberately empty of re-exports. draft_helper imports sleeper_client,
lineup_value imports draft_helper, and eleven modules import paths; any
convenience import here would run at package-init time and turn that
graph into a cycle. Import the module you want.

Entry points live OUTSIDE this package, at the repo root: br.py (the
command), mcp_server.py (Claude Desktop names its absolute path in an
external config file), test_all.py and test_scoring.py.
"""
