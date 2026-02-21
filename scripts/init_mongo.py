#!/usr/bin/env python3
"""
Initialize MongoDB for the ticket-router project.

This script will:
- Connect to the MongoDB URI provided in the MONGO_URI environment variable
- Ensure the `ticket_router` database exists (Mongo creates DB on write)
- Create the `tickets` collection if missing and add useful indexes:
    - created_at (ascending)
    - urgency (descending)
    - text index on subject and body for simple search

Usage:
  export MONGO_URI="mongodb+srv://<user>:<password>@cluster0.xxx.mongodb.net"
  python scripts/init_mongo.py
"""
import os
import sys
from pymongo import MongoClient, ASCENDING, DESCENDING, TEXT


def main():
    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        print("Please set MONGO_URI environment variable (see .env.example).")
        sys.exit(1)

    print("Connecting to MongoDB...")
    client = MongoClient(mongo_uri)

    db = client["ticket_router"]
    coll_name = "tickets"

    if coll_name in db.list_collection_names():
        print(f"Collection '{coll_name}' already exists. Ensuring indexes...")
    else:
        print(f"Creating collection '{coll_name}'...")
        db.create_collection(coll_name)

    tickets = db[coll_name]

    # Create indexes (idempotent)
    print("Creating index: created_at (ASCENDING)...")
    tickets.create_index([("created_at", ASCENDING)], name="idx_created_at")

    print("Creating index: urgency (DESCENDING)...")
    tickets.create_index([("urgency", DESCENDING)], name="idx_urgency_desc")

    print("Creating text index on subject and body...")
    tickets.create_index([("subject", TEXT), ("body", TEXT)], name="idx_text_subject_body")

    print("MongoDB initialization complete.")


if __name__ == "__main__":
    main()

