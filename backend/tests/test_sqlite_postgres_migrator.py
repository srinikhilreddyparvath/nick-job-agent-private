from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import Column, DateTime, ForeignKey, Integer, MetaData, String, Table, create_engine, func, select

from scripts.migrate_sqlite_to_postgres import advance_postgres_sequences, migrate


def test_historical_job_backfill_idempotency_and_foreign_keys(tmp_path):
    source=create_engine(f"sqlite:///{tmp_path/'old.db'}");target=create_engine(f"sqlite:///{tmp_path/'target.db'}")
    old=MetaData();jobs=Table("jobs",old,Column("id",Integer,primary_key=True),Column("company",String,nullable=False),Column("discovered_at",DateTime),Column("created_at",DateTime),Column("updated_at",DateTime),Column("first_seen_at",DateTime),Column("last_seen_at",DateTime),Column("last_verified_at",DateTime));packages=Table("application_packages",old,Column("id",Integer,primary_key=True),Column("job_id",Integer,ForeignKey("jobs.id"),nullable=False));old.create_all(source)
    current=MetaData();current_jobs=Table("jobs",current,Column("id",Integer,primary_key=True),Column("company",String,nullable=False),Column("discovered_at",DateTime),Column("created_at",DateTime),Column("updated_at",DateTime),Column("first_seen_at",DateTime,nullable=False),Column("last_seen_at",DateTime,nullable=False),Column("last_verified_at",DateTime,nullable=False),Column("posting_status",String,nullable=False));current_packages=Table("application_packages",current,Column("id",Integer,primary_key=True),Column("job_id",Integer,ForeignKey("jobs.id"),nullable=False));current.create_all(target)
    stamp=datetime(2026,9,1,tzinfo=timezone.utc)
    with source.begin() as connection:connection.execute(jobs.insert().values(id=1,company="Example AI",discovered_at=stamp,created_at=stamp,updated_at=stamp));connection.execute(packages.insert().values(id=7,job_id=1))
    dry=migrate(source,target,False);assert dry["jobs"]["would_insert"]==1
    migrate(source,target,True);second=migrate(source,target,True)
    with target.connect() as connection:
        row=connection.execute(select(current_jobs)).mappings().one();assert row["first_seen_at"]==stamp.replace(tzinfo=None) and row["last_seen_at"]==stamp.replace(tzinfo=None) and row["last_verified_at"]==stamp.replace(tzinfo=None) and row["posting_status"]=="UNKNOWN"
        assert connection.scalar(select(func.count()).select_from(current_packages))==1 and connection.execute(select(current_packages.c.job_id)).scalar_one()==1
    assert second["jobs"]["would_insert"]==0 and second["application_packages"]["would_insert"]==0


def test_unknown_required_column_rolls_back_entire_migration(tmp_path):
    source=create_engine(f"sqlite:///{tmp_path/'old.db'}");target=create_engine(f"sqlite:///{tmp_path/'target.db'}")
    old=MetaData();good=Table("a_good",old,Column("id",Integer,primary_key=True));bad=Table("z_bad",old,Column("id",Integer,primary_key=True));old.create_all(source)
    current=MetaData();target_good=Table("a_good",current,Column("id",Integer,primary_key=True));Table("z_bad",current,Column("id",Integer,primary_key=True),Column("required_fact",String,nullable=False));current.create_all(target)
    with source.begin() as connection:connection.execute(good.insert().values(id=1));connection.execute(bad.insert().values(id=1))
    with pytest.raises(RuntimeError,match="z_bad.*required_fact"):migrate(source,target,True)
    with target.connect() as connection:assert connection.scalar(select(func.count()).select_from(target_good))==0


def test_postgres_sequence_advancement_uses_maximum_id():
    metadata=MetaData();table=Table("jobs",metadata,Column("id",Integer,primary_key=True));calls=[]
    class FakeConnection:
        dialect=SimpleNamespace(name="postgresql")
        def scalar(self,statement,parameters=None):return "public.jobs_id_seq" if "pg_get_serial_sequence" in str(statement) else 9
        def execute(self,statement,parameters=None):calls.append((str(statement),parameters))
    result=advance_postgres_sequences(FakeConnection(),[table])
    assert result=={"jobs":9} and calls[0][1]["maximum"]==9 and calls[0][1]["sequence"]=="public.jobs_id_seq"
