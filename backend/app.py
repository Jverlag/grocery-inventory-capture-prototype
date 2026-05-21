from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import mysql.connector
import requests
import os

app = Flask(__name__)
CORS(app)
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")

@app.route("/scanner")
def scanner_page():
    return send_from_directory(FRONTEND_DIR, "index.html")

DB_CONFIG = {
    "host": "localhost",
    "user": "CHANGE_ME",            #Replace with your own MySQL credentials 
    "password": "CHANGE_ME",        #Replace with your own MySQL credentials 
    "database": "grocery_tracker"
}

@app.route("/")
def home():
    return jsonify({"ok": True, "message": "Backend is running"})

@app.route("/products")
def products():
    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM products ORDER BY product_id")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(rows)

@app.route("/stores")
def stores():
    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM stores ORDER BY store_id")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(rows)

@app.route("/lookup/<barcode>")
def lookup(barcode):
    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor(dictionary=True)

    cur.execute("SELECT * FROM products WHERE barcode = %s", (barcode,))
    existing = cur.fetchone()

    cur.close()
    conn.close()

    if existing:
        return jsonify({
            "found": True,
            "source": "local_database",
            "barcode": existing["barcode"],
            "product_name": existing["product_name"],
            "brand": existing.get("brand"),
            "category": existing.get("category"),
            "package_size": existing.get("package_size")
        })
    url = f"https://world.openfoodfacts.net/api/v2/product/{barcode}"
    try:
        r = requests.get(url, timeout=15)
        data = r.json()
    except Exception as e:
        return jsonify({
            "found": False,
            "error": f"Request exception: {str(e)}"
        }), 502

    if r.status_code != 200:
        return jsonify({
            "found": False,
            "error": f"API request failed",
            "status_code": r.status_code,
            "response_preview": r.text[:300]
        }), 502

    if data.get("status") != 1:
        return jsonify({
            "found": False,
            "barcode": barcode,
            "status": data.get("status"),
            "status_verbose": data.get("status_verbose")
        })

    product = data.get("product", {})

    return jsonify({
        "found": True,
        "barcode": barcode,
        "product_name": product.get("product_name", ""),
        "brand": product.get("brands", ""),
        "category": product.get("categories", ""),
        "package_size": product.get("quantity", "")
    })

@app.route("/save_product/<barcode>")
def save_product(barcode):
    url = f"https://world.openfoodfacts.net/api/v2/product/{barcode}"

    try:
        r = requests.get(url, timeout=10)
        data = r.json()
    except Exception as e:
        return jsonify({
            "saved": False,
            "error": f"Request exception: {str(e)}"
        }), 502

    if r.status_code != 200:
        return jsonify({
            "saved": False,
            "error": "API request failed",
            "status_code": r.status_code,
            "response_preview": r.text[:300]
        }), 502

    if data.get("status") != 1:
        return jsonify({
            "saved": False,
            "barcode": barcode,
            "status": data.get("status"),
            "status_verbose": data.get("status_verbose")
        })

    product = data.get("product", {})
    product_name = product.get("product_name", "").strip()
    brand = product.get("brands", "").strip()
    category = product.get("categories", "").strip()
    package_size = product.get("quantity", "").strip()

    if not product_name:
        return jsonify({
            "saved": False,
            "error": "Product found in API but product_name is empty"
        }), 400

    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor(dictionary=True)

    try:
        # Check if barcode already exists
        cur.execute("SELECT * FROM products WHERE barcode = %s", (barcode,))
        existing = cur.fetchone()

        if existing:
            cur.execute("""
                UPDATE products
                SET product_name = %s,
                    brand = %s,
                    category = %s,
                    package_size = %s
                WHERE barcode = %s
            """, (product_name, brand, category, package_size, barcode))

            conn.commit()

            return jsonify({
                "saved": True,
                "already_exists": True,
                "message": "Existing product updated successfully",
                "barcode": barcode,
                "product_name": product_name,
                "brand": brand,
                "category": category,
                "package_size": package_size
            })

        # Insert new product
        cur.execute("""
            INSERT INTO products (barcode, product_name, brand, category, package_size)
            VALUES (%s, %s, %s, %s, %s)
        """, (barcode, product_name, brand, category, package_size))

        conn.commit()
        product_id = cur.lastrowid

        return jsonify({
            "saved": True,
            "already_exists": False,
            "message": "Product inserted successfully",
            "product_id": product_id,
            "barcode": barcode,
            "product_name": product_name,
            "brand": brand,
            "category": category,
            "package_size": package_size
        })

    except Exception as e:
        conn.rollback()
        return jsonify({
            "saved": False,
            "error": str(e)
        }), 500

    finally:
        cur.close()
        conn.close()

@app.route("/manual_product", methods=["POST"])
def manual_product():
    data = request.get_json()

    barcode = data.get("barcode", "").strip()
    product_name = data.get("product_name", "").strip()
    brand = data.get("brand", "").strip()
    category = data.get("category", "").strip()
    package_size = data.get("package_size", "").strip()

    if not barcode or not product_name:
        return jsonify({
            "saved": False,
            "error": "barcode and product_name are required"
        }), 400

    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor(dictionary=True)

    try:
        cur.execute("SELECT * FROM products WHERE barcode = %s", (barcode,))
        existing = cur.fetchone()

        if existing:
            cur.execute("""
                UPDATE products
                SET product_name = %s,
                    brand = %s,
                    category = %s,
                    package_size = %s
                WHERE barcode = %s
            """, (product_name, brand, category, package_size, barcode))

            conn.commit()

            return jsonify({
                "saved": True,
                "already_exists": True,
                "message": "Existing product updated manually",
                "barcode": barcode,
                "product_name": product_name,
                "brand": brand,
                "category": category,
                "package_size": package_size
            })

        cur.execute("""
            INSERT INTO products (barcode, product_name, brand, category, package_size)
            VALUES (%s, %s, %s, %s, %s)
        """, (barcode, product_name, brand, category, package_size))

        conn.commit()

        return jsonify({
            "saved": True,
            "already_exists": False,
            "message": "Manual product inserted successfully",
            "barcode": barcode,
            "product_name": product_name,
            "brand": brand,
            "category": category,
            "package_size": package_size
        })

    except Exception as e:
        conn.rollback()
        return jsonify({
            "saved": False,
            "error": str(e)
        }), 500

    finally:
        cur.close()
        conn.close()


@app.route("/start_purchase", methods=["POST"])
def start_purchase():
    data = request.get_json()

    store_id = data.get("store_id")
    receipt_number = data.get("receipt_number", "")

    if not store_id:
        return jsonify({
            "created": False,
            "error": "store_id is required"
        }), 400

    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor(dictionary=True)

    try:
        cur.execute("""
            INSERT INTO purchases (store_id, purchase_date, receipt_number, total_amount)
            VALUES (%s, NOW(), %s, 0)
        """, (store_id, receipt_number))

        conn.commit()
        purchase_id = cur.lastrowid

        return jsonify({
            "created": True,
            "purchase_id": purchase_id,
            "store_id": store_id,
            "receipt_number": receipt_number
        })

    except Exception as e:
        conn.rollback()
        return jsonify({
            "created": False,
            "error": str(e)
        }), 500

    finally:
        cur.close()
        conn.close()

@app.route("/add_purchase_item", methods=["POST"])
def add_purchase_item():
    data = request.get_json()

    purchase_id = data.get("purchase_id")
    barcode = data.get("barcode", "").strip()
    quantity = data.get("quantity", 1)
    unit_price = data.get("unit_price")
    entry_method = data.get("entry_method", "MANUAL")

    if not purchase_id or not barcode or unit_price is None:
        return jsonify({
            "added": False,
            "error": "purchase_id, barcode, and unit_price are required"
        }), 400

    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor(dictionary=True)

    try:
        cur.execute("SELECT product_id, product_name FROM products WHERE barcode = %s", (barcode,))
        product = cur.fetchone()

        if not product:
            return jsonify({
                "added": False,
                "error": "Product barcode not found in products table",
                "barcode": barcode
            }), 404

        cur.execute("""
            INSERT INTO purchase_items (purchase_id, product_id, quantity, unit_price, entry_method)
            VALUES (%s, %s, %s, %s, %s)
        """, (purchase_id, product["product_id"], quantity, unit_price, entry_method))

        cur.execute("""
            UPDATE purchases
            SET total_amount = (
                SELECT COALESCE(SUM(quantity * unit_price), 0)
                FROM purchase_items
                WHERE purchase_id = %s
            )
            WHERE purchase_id = %s
        """, (purchase_id, purchase_id))

        conn.commit()

        return jsonify({
            "added": True,
            "purchase_id": purchase_id,
            "barcode": barcode,
            "product_id": product["product_id"],
            "product_name": product["product_name"],
            "quantity": quantity,
            "unit_price": unit_price
        })

    except Exception as e:
        conn.rollback()
        return jsonify({
            "added": False,
            "error": str(e)
        }), 500

    finally:
        cur.close()
        conn.close()

@app.route("/add_manual_purchase_item", methods=["POST"])
def add_manual_purchase_item():
    data = request.get_json()

    purchase_id = data.get("purchase_id")
    product_name = data.get("product_name")
    category = data.get("category")
    quantity = data.get("quantity", 1)
    unit_price = data.get("unit_price")

    if not purchase_id or not product_name or unit_price is None:
        return jsonify({
            "added": False,
            "error": "purchase_id, product_name, and unit_price are required"
        }), 400

    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor(dictionary=True)

    try:


        cur.execute("""
            SELECT COUNT(*) AS total
            FROM products
            WHERE internal_code IS NOT NULL
        """)

        result = cur.fetchone()
        next_number = result["total"] + 1
        internal_code = f"INT-{next_number:06d}"

        cur.execute("""
            INSERT INTO products (barcode, product_name, brand, category, package_size, internal_code)
            VALUES (NULL, %s, NULL, %s, NULL, %s)
        """, (product_name, category, internal_code))

        product_id = cur.lastrowid

        cur.execute("""
            INSERT INTO purchase_items
            (purchase_id, product_id, quantity, unit_price, entry_method)
            VALUES (%s, %s, %s, %s, %s)
        """, (purchase_id, product_id, quantity, unit_price, "MANUAL"))

        cur.execute("""
            UPDATE purchases
            SET total_amount = (
                SELECT COALESCE(SUM(quantity * unit_price), 0)
                FROM purchase_items
                WHERE purchase_id = %s
            )
            WHERE purchase_id = %s
        """, (purchase_id, purchase_id))

        conn.commit()

        return jsonify({
            "added": True,
            "purchase_id": purchase_id,
            "product_id": product_id,
            "product_name": product_name,
            "quantity": quantity,
            "unit_price": unit_price,
            "entry_method": "MANUAL"
        })

    except Exception as e:
        conn.rollback()
        return jsonify({
            "added": False,
            "error": str(e)
        }), 500

    finally:
        cur.close()
        conn.close()




@app.route("/get_purchase/<int:purchase_id>")
def get_purchase(purchase_id):
    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor(dictionary=True)

    try:
        cur.execute("""
            SELECT 
                p.purchase_id,
                p.store_id,
                s.store_name,
                p.purchase_date,
                p.receipt_number,
                p.total_amount
            FROM purchases p
            JOIN stores s ON p.store_id = s.store_id
            WHERE p.purchase_id = %s
        """, (purchase_id,))
        purchase = cur.fetchone()

        if not purchase:
            return jsonify({
                "found": False,
                "error": "Purchase not found"
            }), 404

        cur.execute("""
            SELECT
                pi.purchase_item_id,
                pr.product_name,
                pr.barcode,
                pi.quantity,
                pi.unit_price,
                (pi.quantity * pi.unit_price) AS subtotal
            FROM purchase_items pi
            JOIN products pr ON pi.product_id = pr.product_id
            WHERE pi.purchase_id = %s
            ORDER BY pi.purchase_item_id
        """, (purchase_id,))
        items = cur.fetchall()

        return jsonify({
            "found": True,
            "purchase": purchase,
            "items": items
        })

    except Exception as e:
        return jsonify({
            "found": False,
            "error": str(e)
        }), 500

    finally:
        cur.close()
        conn.close()



@app.route("/finish_purchase/<int:purchase_id>", methods=["POST"])
def finish_purchase(purchase_id):
    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor(dictionary=True)

    try:
        cur.execute("""
            UPDATE purchases
            SET status = 'FINISHED'
            WHERE purchase_id = %s
        """, (purchase_id,))

        conn.commit()

        return jsonify({
            "finished": True,
            "purchase_id": purchase_id
        })

    except Exception as e:
        conn.rollback()
        return jsonify({
            "finished": False,
            "error": str(e)
        }), 500

    finally:
        cur.close()
        conn.close()






if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
