from dao import db


def process_inbox():
    """
    Fetches unprocessed items from the inbox and updates the People table.
    """
    print("Checking inbox for new data...")
    items = db.get_unprocessed_inbox_items()

    if not items:
        print("Inbox is empty.")
        return

    for item in items:
        print(f"Processing Inbox Item {item['id']} ({item['source_name']})...")

        try:
            # Handle CSV Payloads
            if item["source_type"] == "csv":
                process_csv_payload(item["raw_payload"])

            # Handle Form Payloads (Placeholder logic)
            elif item["source_type"] == "google_form":
                # TODO: Implement form specific logic
                pass

            # Mark as Success
            db.mark_inbox_processed(item["id"])
            print(f"Successfully processed item {item['id']}")

        except Exception as e:
            print(f"Failed to process item {item['id']}: {e}")
            db.mark_inbox_processed(item["id"], error=str(e))


def process_csv_payload(records):
    """
    Iterates through rows and Upserts people.
    """
    stats = {"new": 0, "updated": 0, "skipped": 0}

    # Define mapping strategies (Common CSV headers to DB columns)
    # We prioritize specific keys for the 'strict' columns

    for row in records:
        # 1. Find Email (Mandatory)
        email = row.get("email") or row.get("email_address")
        if not email:
            stats["skipped"] += 1
            continue

        # 2. Find Name
        full_name = (
            row.get("full_name")
            or row.get("name")
            or f"{row.get('first_name', '')} {row.get('last_name', '')}".strip()
        )

        # 3. Find Phone
        phone = row.get("phone") or row.get("phone_number") or row.get("whatsapp")

        # 4. Find Role
        role = row.get("role", "student")  # Default to student
        if role not in ["student", "professor", "admin", "external"]:
            role = "student"  # Fallback if invalid role text

        # 5. Extract Profile Data (Everything else)
        # We remove the strict keys so we don't duplicate data in JSONB
        strict_keys = [
            "email",
            "email_address",
            "full_name",
            "name",
            "first_name",
            "last_name",
            "phone",
            "phone_number",
            "role",
        ]
        profile_data = {k: v for k, v in row.items() if k not in strict_keys}

        # 6. Upsert to DAO
        db.upsert_person(
            email=email,
            full_name=full_name,
            phone=str(phone) if phone else None,
            role=role,
            extra_data=profile_data,
        )
        stats["updated"] += 1  # Upsert counts as update for simplicity

    print(f"Batch Result: {stats}")
