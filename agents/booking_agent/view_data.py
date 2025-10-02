import sqlite3

def view_table(conn, table_name):
    cur = conn.cursor()
    print(f"\n===== {table_name.upper()} =====")
    try:
        rows = cur.execute(f"SELECT * FROM {table_name}").fetchall()
        col_names = [desc[0] for desc in cur.description]

        if rows:
            print("\t".join(col_names))
            for row in rows:
                print("\t".join(str(x) for x in row))
        else:
            print("(No data)")
    except sqlite3.Error as e:
        print(f"Error reading {table_name}: {e}")

def main():
    conn = sqlite3.connect("schedule.db")

    for table in ["doctors", "work_shifts", "shift_exceptions", "appointments"]:
        view_table(conn, table)

    conn.close()

if __name__ == "__main__":
    main()