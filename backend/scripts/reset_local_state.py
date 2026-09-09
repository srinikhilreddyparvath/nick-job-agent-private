import argparse

from app.db.database import SessionLocal
from app.services.local_state_service import LocalStateService


def main():
    parser=argparse.ArgumentParser(description="Reset generated Career Agent user state without deleting environment secrets or examples")
    parser.add_argument("--confirm",required=True,help='Must be exactly "RESET ROLECALL"')
    args=parser.parse_args()
    with SessionLocal() as db:result=LocalStateService().reset(db,args.confirm)
    print(f"Local state reset: {result['database_tables_cleared']} database tables cleared; {result['candidate_files_removed']} candidate files removed")


if __name__=="__main__":main()
