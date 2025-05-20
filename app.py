import os
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_mail import Mail
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from functools import wraps
from pymongo import ASCENDING, DESCENDING

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY") or "devsecret"

app.config['MAIL_SERVER'] = 'smtp.gmail.com'   # Example: Gmail SMTP server
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')   # Your email
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')   # App password or real password (better to use env vars)
app.config['MAIL_DEFAULT_SENDER'] = ('My Restaurant', 'your-email@gmail.com')

mail = Mail(app) 

client = MongoClient(os.getenv("MONGO_URI"))
db = client.get_database()

# ------------------------ Helpers ------------------------
def admin_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            flash("Please login as admin.")
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated

# ------------------------ Customer Routes ------------------------

@app.route("/")
def index():
    search = request.args.get("search", "").strip()
    category = request.args.get("category", "").strip()
    sort = request.args.get("sort", "").strip()

    query = {}

    # Search by name or description (case insensitive)
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}},
        ]

    # Category filter
    if category:
        query["category"] = category

    cursor = db.menu.find(query)

    # Sorting options
    if sort == "price_asc":
        cursor = cursor.sort("price", ASCENDING)
    elif sort == "price_desc":
        cursor = cursor.sort("price", DESCENDING)
    elif sort == "popularity_desc":
        cursor = cursor.sort("popularity", DESCENDING)
    elif sort == "rating_desc":
        cursor = cursor.sort("rating", DESCENDING)
    else:
        cursor = cursor.sort("name", ASCENDING)  # Default sort by name

    menu = list(cursor)

    return render_template("menu.html", menu=menu)

@app.route("/add_to_cart/<item_id>", methods=["POST"])
def add_to_cart(item_id):
    item = db.menu.find_one({"_id": ObjectId(item_id)})
    if not item:
        flash("Menu item not found.")
        return redirect(url_for("index"))

    quantity = int(request.form.get("quantity", 1))
    if quantity < 1:
        flash("Invalid quantity.")
        return redirect(url_for("index"))

    cart = session.get("cart", {})
    if item_id in cart:
        cart[item_id]["quantity"] += quantity
    else:
        cart[item_id] = {
            "name": item["name"],
            "price": float(item["price"]),
            "quantity": quantity
        }
    session["cart"] = cart
    flash(f"Added {quantity} x {item['name']} to cart.")
    return redirect(url_for("index"))

@app.route("/cart")
def view_cart():
    cart = session.get("cart", {})
    total = sum(item["price"] * item["quantity"] for item in cart.values())
    return render_template("cart.html", cart=cart, total=total)

@app.route("/update_cart", methods=["POST"])
def update_cart():
    cart = session.get("cart", {})
    for item_id in list(cart.keys()):
        qty = request.form.get(f"quantity_{item_id}")
        if qty:
            try:
                qty = int(qty)
                if qty < 1:
                    cart.pop(item_id)
                else:
                    cart[item_id]["quantity"] = qty
            except ValueError:
                pass
    session["cart"] = cart
    flash("Cart updated.")
    return redirect(url_for("view_cart"))

@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    cart = session.get("cart", {})
    if not cart:
        flash("Your cart is empty!")
        return redirect(url_for("index"))

    if request.method == "POST":
        delivery_option = request.form.get("delivery_option")
        if delivery_option not in ["Pickup", "Delivery"]:
            flash("Please select a valid delivery option.")
            return redirect(url_for("checkout"))

        order_doc = {
            "items": [],
            "delivery_option": delivery_option,
            "status": "Pending"
        }

        if delivery_option == "Pickup":
            pickup_type = request.form.get("pickup_type")
            if pickup_type not in ["Parcel", "Dining"]:
                flash("Please select a valid pickup type.")
                return redirect(url_for("checkout"))
            order_doc["pickup_type"] = pickup_type

            if pickup_type == "Dining":
                table_number = request.form.get("table_number")
                if not table_number:
                    flash("Please enter your table number for dining pickup.")
                    return redirect(url_for("checkout"))
                order_doc["table_number"] = table_number

        elif delivery_option == "Delivery":
            phone_number = request.form.get("phone_number")
            if not phone_number:
                flash("Please enter your phone number for delivery.")
                return redirect(url_for("checkout"))
            order_doc["phone_number"] = phone_number

        for item_id, details in cart.items():
            order_doc["items"].append({
                "item_id": ObjectId(item_id),
                "name": details["name"],
                "quantity": details["quantity"],
                "price": details["price"]
            })

        db.orders.insert_one(order_doc)
        session.pop("cart")
        flash("Order placed successfully!")
        return redirect(url_for("index"))

    total = sum(item["price"] * item["quantity"] for item in cart.values())
    return render_template("checkout.html", cart=cart, total=total)

# ------------------------ Admin Auth ------------------------

@app.route("/admin/register", methods=["GET", "POST"])
def admin_register():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        if db.admins.find_one({"username": username}):
            flash("Username already exists.")
            return redirect(url_for("admin_register"))
        hashed = generate_password_hash(password)
        db.admins.insert_one({"username": username, "password_hash": hashed})
        flash("Admin registered.")
        return redirect(url_for("admin_login"))
    return render_template("register.html")

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        admin = db.admins.find_one({"username": username})
        if admin and check_password_hash(admin["password_hash"], password):
            session["admin_logged_in"] = True
            session["admin_username"] = username
            flash("Login successful.")
            return redirect(url_for("admin_dashboard"))
        flash("Invalid credentials.")
    return render_template("login.html")

@app.route("/admin/logout")
@admin_login_required
def admin_logout():
    session.clear()
    flash("Logged out.")
    return redirect(url_for("admin_login"))

# ------------------------ Admin Panel ------------------------

@app.route("/admin")
@admin_login_required
def admin_dashboard():
    menu = list(db.menu.find())
    orders = list(db.orders.find())
    return render_template("admin_dashboard.html", menu=menu, orders=orders)

@app.route("/admin/menu/add", methods=["GET", "POST"])
@admin_login_required
def admin_add_menu():
    name = request.form.get("name")
    price = float(request.form.get("price"))
    description = request.form.get("description", "")
    image_url = request.form.get("image_url", "")
    category = request.form.get("category")
    popularity = int(request.form.get("popularity", 0))
    rating = float(request.form.get("rating", 0))

    # Check if item with this name already exists
    existing_item = db.menu.find_one({"name": name})

    menu_item = {
        "name": name,
        "price": price,
        "description": description,
        "image_url": image_url,
        "category": category,
        "popularity": popularity,
        "rating": rating,
    }

    if existing_item:
        # Update existing
        db.menu.update_one({"_id": existing_item["_id"]}, {"$set": menu_item})
        flash(f"Menu item '{name}' updated.", "success")
    else:
        # Insert new
        db.menu.insert_one(menu_item)
        flash(f"Menu item '{name}' added.", "success")

    return redirect(url_for("admin_dashboard"))

@app.route("/admin/menu/edit/<item_id>", methods=["GET", "POST"])
@admin_login_required
def admin_edit_menu(item_id):
    item = db.menu.find_one({"_id": ObjectId(item_id)})
    if not item:
        flash("Item not found.")
        return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        name = request.form.get("name")
        description = request.form.get("description")
        price = float(request.form.get("price", 0))
        image_url = request.form.get("image_url")
        if not name or price <= 0:
            flash("Invalid input.")
            return redirect(url_for("admin_edit_menu", item_id=item_id))
        db.menu.update_one(
            {"_id": ObjectId(item_id)},
            {"$set": {"name": name, "description": description, "price": price, "image_url": image_url}}
        )
        flash("Item updated.")
        return redirect(url_for("admin_dashboard"))
    return render_template("admin_edit_menu.html", item=item)

@app.route("/admin/menu/delete/<item_id>", methods=["POST"])
@admin_login_required
def admin_delete_menu(item_id):
    db.menu.delete_one({"_id": ObjectId(item_id)})
    flash("Item deleted.")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/orders/update", methods=["POST"])
@admin_login_required
def update_order_status():
    try:
        data = request.get_json()
        order_id = data.get("order_id")
        status = data.get("status")
        if not order_id or not status:
            return jsonify({"error": "Missing data"}), 400
        oid = ObjectId(order_id)
        if status == "Completed":
            result = db.orders.delete_one({"_id": oid})
            if result.deleted_count == 0:
                return jsonify({"error": "Order not found"}), 404
        else:
            result = db.orders.update_one({"_id": oid}, {"$set": {"status": status}})
            if result.matched_count == 0:
                return jsonify({"error": "Order not found"}), 404
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/admin/orders")
@admin_login_required
def admin_orders():
    orders = list(db.orders.find())
    for order in orders:
        if not order.get("items"):
            order["items"] = []
    return render_template("admin_orders.html", orders=orders)

# ------------------------

if __name__ == "__main__":
    app.run(debug=True)
