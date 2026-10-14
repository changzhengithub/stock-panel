"""Immutable industry-chain revisions and graph reference constraints."""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

STATEMENTS = (
    "CREATE TABLE industry_chains (\n\tid VARCHAR NOT NULL, \n\tname VARCHAR NOT NULL, \n\tpublished_revision VARCHAR, \n\tPRIMARY KEY (id)\n)",
    "CREATE TABLE chain_revisions (\n\tid VARCHAR NOT NULL, \n\tchain_id VARCHAR NOT NULL, \n\tcontent_hash VARCHAR NOT NULL, \n\tpayload JSON NOT NULL, \n\tstate VARCHAR NOT NULL, \n\tcreated_at VARCHAR NOT NULL, \n\treviewed_at VARCHAR, \n\treviewer VARCHAR, \n\treview_note VARCHAR, \n\tpublished_at VARCHAR, \n\tPRIMARY KEY (id), \n\tUNIQUE (chain_id, content_hash), \n\tFOREIGN KEY(chain_id) REFERENCES industry_chains (id)\n)",
    "CREATE INDEX ix_chain_revisions_chain_id ON chain_revisions (chain_id)",
    'CREATE TABLE chain_nodes (\n\trevision_id VARCHAR NOT NULL, \n\t"key" VARCHAR NOT NULL, \n\tpayload JSON NOT NULL, \n\tPRIMARY KEY (revision_id, "key"), \n\tFOREIGN KEY(revision_id) REFERENCES chain_revisions (id)\n)',
    'CREATE TABLE chain_sources (\n\trevision_id VARCHAR NOT NULL, \n\t"key" VARCHAR NOT NULL, \n\tsnapshot_hash VARCHAR NOT NULL, \n\tpayload JSON NOT NULL, \n\tPRIMARY KEY (revision_id, "key"), \n\tFOREIGN KEY(revision_id) REFERENCES chain_revisions (id)\n)',
    'CREATE TABLE chain_edges (\n\trevision_id VARCHAR NOT NULL, \n\t"key" VARCHAR NOT NULL, \n\tsource VARCHAR NOT NULL, \n\ttarget VARCHAR NOT NULL, \n\tpayload JSON NOT NULL, \n\tPRIMARY KEY (revision_id, "key"), \n\tFOREIGN KEY(revision_id, source) REFERENCES chain_nodes (revision_id, "key"), \n\tFOREIGN KEY(revision_id, target) REFERENCES chain_nodes (revision_id, "key"), \n\tFOREIGN KEY(revision_id) REFERENCES chain_revisions (id)\n)',
    'CREATE TABLE chain_stock_links (\n\trevision_id VARCHAR NOT NULL, \n\t"key" VARCHAR NOT NULL, \n\tnode_key VARCHAR NOT NULL, \n\tts_code VARCHAR NOT NULL, \n\tpayload JSON NOT NULL, \n\tPRIMARY KEY (revision_id, "key"), \n\tFOREIGN KEY(revision_id, node_key) REFERENCES chain_nodes (revision_id, "key"), \n\tFOREIGN KEY(revision_id) REFERENCES chain_revisions (id)\n)',
    "CREATE INDEX ix_chain_stock_links_ts_code ON chain_stock_links (ts_code)",
    'CREATE TABLE chain_evidence (\n\trevision_id VARCHAR NOT NULL, \n\t"key" VARCHAR NOT NULL, \n\tsource_key VARCHAR NOT NULL, \n\ttarget_kind VARCHAR NOT NULL, \n\ttarget_key VARCHAR NOT NULL, \n\tpayload JSON NOT NULL, \n\tPRIMARY KEY (revision_id, "key"), \n\tFOREIGN KEY(revision_id, source_key) REFERENCES chain_sources (revision_id, "key")\n)',
    'CREATE TABLE chain_analyses (\n\trevision_id VARCHAR NOT NULL, \n\t"key" VARCHAR NOT NULL, \n\tnode_key VARCHAR NOT NULL, \n\tpayload JSON NOT NULL, \n\tPRIMARY KEY (revision_id, "key"), \n\tFOREIGN KEY(revision_id, node_key) REFERENCES chain_nodes (revision_id, "key")\n)',
    'CREATE TABLE chain_business_metrics (\n\trevision_id VARCHAR NOT NULL, \n\t"key" VARCHAR NOT NULL, \n\tlink_key VARCHAR NOT NULL, \n\tpayload JSON NOT NULL, \n\tPRIMARY KEY (revision_id, "key"), \n\tFOREIGN KEY(revision_id, link_key) REFERENCES chain_stock_links (revision_id, "key")\n)',
    'CREATE TABLE chain_leader_claims (\n\trevision_id VARCHAR NOT NULL, \n\t"key" VARCHAR NOT NULL, \n\tlink_key VARCHAR NOT NULL, \n\tpayload JSON NOT NULL, \n\tPRIMARY KEY (revision_id, "key"), \n\tFOREIGN KEY(revision_id, link_key) REFERENCES chain_stock_links (revision_id, "key")\n)',
    "CREATE TABLE chain_import_runs (\n\tid VARCHAR NOT NULL, \n\tchain_id VARCHAR NOT NULL, \n\tinput_hash VARCHAR NOT NULL, \n\trevision_id VARCHAR, \n\tstate VARCHAR NOT NULL, \n\tstarted_at VARCHAR NOT NULL, \n\tfinished_at VARCHAR, \n\terror VARCHAR, \n\tPRIMARY KEY (id)\n)",
)
TABLES = (
    "industry_chains",
    "chain_revisions",
    "chain_nodes",
    "chain_sources",
    "chain_edges",
    "chain_stock_links",
    "chain_evidence",
    "chain_analyses",
    "chain_business_metrics",
    "chain_leader_claims",
    "chain_import_runs",
)


def upgrade():
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade():
    for name in reversed(TABLES):
        op.drop_table(name)
