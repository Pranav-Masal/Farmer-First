from flask import Flask, render_template, request, redirect, session, flash, url_for, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from langchain_groq import ChatGroq
import os

import smtplib
from email.mime.text import MIMEText

load_dotenv()

app = Flask(__name__)
app.secret_key = "secret123"

# ---------------- AI ----------------

llm = ChatGroq(
    model="openai/gpt-oss-120b",
    api_key=os.getenv("GROQ_API_KEY")
)

# ---------------- MONGODB CONFIG ----------------

client = MongoClient("mongodb+srv://Farmer-First:root@cluster0.p3rfmg3.mongodb.net/?appName=Cluster0")
db = client["farmer-first"]

users_collection = db["users"]
products_collection = db["products"]
farmers_collection = db["farmers"]

# ---------------- IMAGE UPLOAD ----------------

UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# ---------------- HOME ----------------

@app.route('/')
def index():
    return render_template("index.html")

# ---------------- REGISTER ----------------

@app.route('/register', methods=['GET','POST'])
def register():

    if request.method == 'POST':

        name = request.form['name']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])
        role = request.form['role']

        users_collection.insert_one({
            "name": name,
            "email": email,
            "password": password,
            "role": role
        })

        flash("Registered Successfully")
        return redirect('/login')

    return render_template("register.html")

# ---------------- LOGIN ----------------

@app.route('/login', methods=['GET','POST'])
def login():

    if request.method == 'POST':

        email = request.form['email']
        password = request.form['password']

        user = users_collection.find_one({"email": email})

        if user and check_password_hash(user["password"], password):

            session['user_id'] = str(user["_id"])
            session['role'] = user["role"]

            return redirect('/dashboard')

        else:
            flash("Invalid Credentials")

    return render_template("login.html",isLoggedIn=('user_id' in session))

# ---------------- DASHBOARD ----------------

@app.route('/dashboard')
def dashboard():

    if 'user_id' not in session:
        return redirect('/login')

    products = list(products_collection.find())
    fresh_products = list(products_collection.find().sort("_id",-1).limit(8))

    return render_template(
        "dashboard.html",
        products=products,
        fresh_products=fresh_products
    )








# ---------------- pop login ----------------

@app.context_processor
def inject_user():
    return dict(isLoggedIn=('user_id' in session))
# ---------------- searchbar ----------------
@app.route("/live-search")
def live_search():

    query = request.args.get("q")

    products = products_collection.find({
        "name": {"$regex": query, "$options": "i"}
    })

    result = []

    for p in products:
        result.append({
            "name": p["name"],
            "farmer": p["farmer_name"],
            "quantity": p["quantity"],
            "price": p["price"],
            "image": p["image"]
        })

    return jsonify(result)

# ---------------- ADD PRODUCT ----------------

@app.route('/add_product', methods=['POST'])
def add_product():

    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']

    farmer_name = request.form['farmer_name']
    address = request.form['address']
    phone = request.form['phone']

    name = request.form['name']
    price = request.form['price']
    quantity = request.form['quantity']
    description = request.form['description']

    category = predict_category(name)

    image = request.files['image']
    filename = secure_filename(image.filename)
    image.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    products_collection.insert_one({

        "user_id": user_id,
        "farmer_name": farmer_name,
        "address": address,
        "phone": phone,
        "name": name,
        "price": price,
        "quantity": quantity,
        "description": description,
        "category": category,
        "image": filename
    })

    return redirect('/profile')

# ---------------- PRODUCTS ----------------

@app.route('/products')
def products():

    products = list(products_collection.find())

    return render_template("products.html", products=products)

# ---------------- PROFILE ----------------

@app.route('/profile')
def profile():

    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']

    user = users_collection.find_one({"_id": ObjectId(user_id)})
    products = list(products_collection.find({"user_id": user_id}))

    return render_template("profile.html", user=user, products=products)

# ---------------- product delete ----------------
@app.route('/delete_product/<product_id>', methods=['POST'])
def delete_product(product_id):
    products_collection.delete_one({'_id': ObjectId(product_id)})
    return redirect(url_for('your_products_page'))  # replace with your products page route

# ---------------- FARMER REGISTER ----------------

@app.route('/farmer-register', methods=['GET','POST'])
def farmer_register():

    if 'user_id' not in session:
        return redirect('/login')

    if request.method == 'POST':

        user_id = session['user_id']

        name = request.form['name']
        phone = request.form['phone']
        address = request.form['address']

        latitude = request.form.get('latitude')
        longitude = request.form.get('longitude')

        photo = request.files['photo']
        filename = secure_filename(photo.filename)
        photo.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        farmers_collection.insert_one({
            "user_id": user_id,
            "name": name,
            "phone": phone,
            "address": address,
            "photo": filename,
            "rating": 0,
            "latitude": float(latitude) if latitude else None,
            "longitude": float(longitude) if longitude else None
        })

        return redirect('/farmer-show')

    return render_template("farmer_register.html")

# ---------------- FARMER LOCATION ----------------
@app.route('/farmers-location')
def farmers_location():

    farmers = farmers_collection.find()

    data = []

    for f in farmers:
        if f.get("latitude") and f.get("longitude"):

            # get farmer products
            farmer_products = list(products_collection.find({
                "user_id": str(f["user_id"])
            }))

            product_names = [p["name"] for p in farmer_products]

            data.append({
                "name": f["name"],
                "phone": f["phone"],
                "products": product_names if product_names else [],
                "address": f["address"],
                "latitude": f["latitude"],
                "longitude": f["longitude"]
            })

    return jsonify(data)
# ---------------- FARMER SHOW ----------------

@app.route('/farmer-show')
def farmer_show():

    farmers = list(farmers_collection.find().sort("_id",-1))

    return render_template("farmer_show.html", farmers=farmers)

# ---------------- ALL FARMERS ----------------

@app.route('/farmers')
def show_farmers():

    farmers = list(farmers_collection.find().sort("_id",-1))

    return render_template("farmers.html", farmers=farmers)

# ---------------- RATING ----------------

@app.route('/rate/<farmer_id>/<int:rating>')
def rate(farmer_id, rating):

    farmers_collection.update_one(

        {"_id": ObjectId(farmer_id)},
        {"$set": {"rating": rating}}
    )

    return redirect('/farmer-show')

# ---------------- STORY ----------------

@app.route('/story')
def story():
    return render_template("our_story.html")

# ---------------- ORGANIC ----------------

@app.route('/organic')
def organic():
    return render_template("organic.html")

# ---------------- CHEMICAL ----------------

@app.route('/chemical')
def chemical():
    return render_template("chemical.html")

# ---------------- SERVICES ----------------

@app.route('/services')
def services():
    return render_template("services.html")

# ---------------- CONTACT ----------------

@app.route('/contact')
def contact():
    return render_template("contact_page.html")

# ---------------- SHOP ----------------

@app.route("/shop")
def shop():

    products = list(products_collection.find())

    return render_template("shop_now.html", products=products)

# ---------------- CATEGORY PREDICTION ----------------

def predict_category(product_name):

    product_name = product_name.lower()

    vegetables = [
        "onion","potato","cucumber","tomato","carrot","cabbage",
        "spinach","broccoli","cauliflower","pepper"
    ]

    fruits = [
        "apple","banana","mango","grapes","pineapple",
        "dragon fruit","orange","papaya","Green Apple","black"
    ]

    grains = [
        "rice","wheat","corn","barley","oats"
    ]

    if product_name in vegetables:
        return "vegetable"

    elif product_name in fruits:
        return "fruit"

    elif product_name in grains:
        return "grain"

    else:
        return "other"

# ---------------- EXPERT TALK ----------------

@app.route("/expert")
def expert():
    return render_template("expert_talk.html")

@app.route("/ask_expert", methods=["POST"])
def ask_expert():

    question = request.json["question"]

    prompt = f"""
You are the AI assistant of the Farmer First website.

About the Website:
Farmer First is an agriculture platform where farmers can sell their products directly to customers without middlemen.ceo of website is Pranav Masal

Website Features:
1. Farmers can register and create a farmer profile.
2. Farmers can upload products with name, price, category and image.
3. Customers can browse all products on the website.
4. Customers can directly contact farmers using the phone number shown with the product.
5. Farmers have ratings based on customer feedback.
6. The goal of the website is to help farmers get better prices and connect with buyers.

Your Job:
- Help users understand how the website works.
- Guide farmers on how to sell their crops.
- Guide customers on how to buy products.
- Answer farming related questions if possible.
- Always give clear and simple answers.

Rules:
- Use simple English.
- Do not use markdown symbols like ** or ###.
- Do not create tables.
-give answer in line by line
- Give answers in short steps if needed.
-do not give answer of un related to farmer first

User Question:
{question}
"""

    response = llm.invoke(prompt)

    return jsonify({"answer": response.content})

# ---------------- REVIEW ----------------

@app.route('/review')
def review():
    return render_template("review.html")


# ---------------- submit REVIEW ----------------
# Form submit
@app.route('/submit_review', methods=['POST'])
def submit_review():

    name = request.form['name']
    message = request.form['message']

    sender_email = "pranavmasal0273@gmail.com"
    receiver_email = "pranavmasal0273@gmail.com"
    password = "xgmzsqehknyduajh"

    subject = "New Review From Website"

    body = f"""
New Customer Review

Name: {name}

Message:
{message}
"""

    msg = MIMEText(body)

    msg['Subject'] = subject
    msg['From'] = sender_email
    msg['To'] = receiver_email

    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(sender_email, password)
    server.sendmail(sender_email, receiver_email, msg.as_string())
    server.quit()

    return redirect(url_for('review'))
# ---------------- map ----------------
@app.route('/farmers-map')
def farmers_map():
    return render_template("farmers_map.html")


# ---------------- stats home----------------
@app.route("/")
def home():
    farmers_count = farmers_collection.count_documents({})
    products_count = products_collection.count_documents({})
    users_count = users_collection.count_documents({})

    return render_template("index.html",
        farmers=farmers_count,
        products=products_count,
        users=users_count
    )
# ---------------- stats----------------
@app.route("/stats")
def stats():
    return jsonify({
        "farmers": farmers_collection.count_documents({}),
        "products": products_collection.count_documents({}),
        "users": users_collection.count_documents({})
    })
# ---------------- about us ----------------
@app.route('/about')
def about_us():
    return render_template("about_us.html")

# ---------------- LOGOUT ----------------

@app.route('/logout')
def logout():

    session.clear()
    return redirect('/')

# ---------------- RUN APP ----------------

if __name__ == "__main__":
    app.run(debug=True)