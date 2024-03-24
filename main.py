from functools import wraps
from hashlib import scrypt
from flask import Flask, render_template, request, redirect, url_for, session, flash
from pymongo import MongoClient
from bson.objectid import ObjectId
import os
from datetime import datetime
from flask_wtf import FlaskForm
from wtforms import TextAreaField, SubmitField
from wtforms.validators import DataRequired, Length
import re
from datetime import datetime
from flask import jsonify
import requests
from pysafebrowsing import SafeBrowsing
import language_tool_python
import textstat
import oauth
from authlib.integrations.flask_client import OAuth
from passlib.hash import argon2









app = Flask(__name__)
app.secret_key = os.urandom(24) 
client = MongoClient('mongodb+srv://younes:VZt3wNguzosrO4TR@cluster0.nqb3ixv.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0')
db = client['auth'] 
collection = db['forma'] 
collection1= db['malicious_links']
collection2= db['spam_emails']

app.config['GOOGLE_CLIENT_ID'] = '724735319865-a8j63fv13vfo17pk7ra48ue1dq54rmlr.apps.googleusercontent.com'
app.config['GOOGLE_CLIENT_SECRET'] = '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'


oauth = OAuth(app)
oauth.register(
    name='Shieldmail',
    client_id=app.config['GOOGLE_CLIENT_ID'],  
    client_secret=app.config['GOOGLE_CLIENT_SECRET'], 
    access_token_url='https://oauth2.googleapis.com/token',
    authorize_url='https://accounts.google.com/o/oauth2/auth',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)

class EmailAnalyzer:
    def __init__(self, perspective_api_key):
        self.tool = language_tool_python.LanguageTool('auto')
        self.api_key = perspective_api_key

    def included_urls(self,text):
        url_pattern = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
        urls = re.findall(url_pattern, text)
        return urls

    def detect_phishing(self,text):
        endpoint = "https://safebrowsing.googleapis.com/v4/threatMatches:find"
        api_url = f"{endpoint}?key={self.api_key}"

        for url in self.included_urls(text):
            request_body = {
                "client": {
                    "clientId": "wad-itmo-shieldmail",
                    "clientVersion": "1.0",
                },
                "threatInfo": {
                    "threatTypes": ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE"],
                    "platformTypes": ["ANY_PLATFORM"],
                    "threatEntryTypes": ["URL"],
                    "threatEntries": [{"url": url}],
                },
            }

            response = requests.post(api_url, json=request_body)
            response_data = response.json()

            if "matches" in response_data:
                return True

        return False

    def detect_spam(self,text):
        endpoint = "https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze"

        params = {"key": self.api_key}
        data = {
            "comment": {"text": text},
            "languages": ["en"],
            "requestedAttributes": {
                "SPAM": {},
            },
        }

        response = requests.post(endpoint, params=params, json=data)
        results = response.json()

        spam_score = results["attributeScores"]["SPAM"]["summaryScore"]["value"]
        return True if (spam_score > 0.7) else False

    def lexical_diversity(self, text):
        nosign_text = re.sub(r'[^\w\s]', '', text)
        words = nosign_text.lower().split()
        unique_words = set(words)
        lexical_diversity = len(unique_words) / len(words)
        lexical_diversity = round(lexical_diversity, 2)

        return lexical_diversity

    def grammar_checker(self, text):
        grammar_issues = self.tool.check(text)
        return len(grammar_issues)
    
    def spam_score(self, text):
        # Adjusted to accept 'text' parameter
        endpoint = "https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze"
        params = {"key": self.api_key}
        data = {
            "comment": {"text": text},  # Use 'text' parameter
            "languages": ["en"],
            "requestedAttributes": {"SPAM": {}},
        }
        response = requests.post(endpoint, params=params, json=data)
        results = response.json()
        spam_score = results["attributeScores"]["SPAM"]["summaryScore"]["value"]
        return round(spam_score, 2)
    
    def incoherence_score(self, text):
        # Adjusted to accept 'text' parameter
        endpoint = "https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze"
        params = {"key": self.api_key}
        data = {
            "comment": {"text": text},  # Use 'text' parameter
            "languages": ["en"],
            "requestedAttributes": {"INCOHERENT": {}},
        }
        response = requests.post(endpoint, params=params, json=data)
        results = response.json()
        incoherent_score = results["attributeScores"]["INCOHERENT"]["summaryScore"]["value"]
        return round(incoherent_score, 2)
    def toxicity_score(self, text):
        # Adjusted to accept 'text' parameter
        endpoint = "https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze"
        params = {"key": self.api_key}
        data = {
            "comment": {"text": text},  # Use 'text' parameter
            "languages": ["en"],
            "requestedAttributes": {"TOXICITY": {}},
        }
        response = requests.post(endpoint, params=params, json=data)
        results = response.json()
        toxicity_score = results["attributeScores"]["TOXICITY"]["summaryScore"]["value"]
        return round(toxicity_score, 2)

    def flesch_reading_ease(self, text):
        sentences = re.split(r'[.!?]', text)
        sentence_lengths = [len(re.findall(r'\b\w+\b', sentence)) for sentence in sentences if sentence.strip()]
        avg_sentence_length = sum(sentence_lengths) / len(sentence_lengths) if len(sentence_lengths) > 0 else 0

        words = re.findall(r'\b\w+\b', text)
        total_syllables = sum(textstat.syllable_count(word) for word in words)
        avg_syllables_per_word = total_syllables / len(words) if len(words) > 0 else 0

        flesch_score = 206.835 - (1.015 * avg_sentence_length) - (84.6 * avg_syllables_per_word)
        flesch_score = round(min(flesch_score, 100), 2)

        return min(flesch_score, 100)

    def analyze_text_with_perspective(self, text):
        endpoint = "https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze"

        params = {"key": self.api_key}
        data = {
            "comment": {"text": text},
            "languages": ["en"],
            "requestedAttributes": {
                "TOXICITY": {},
                "SPAM": {},
                "INSULT": {},
                "INCOHERENT": {},
            },
        }

        response = requests.post(endpoint, params=params, json=data)
        results = response.json()

        toxicity_score = results["attributeScores"]["TOXICITY"]["summaryScore"]["value"]
        spam_score = results["attributeScores"]["SPAM"]["summaryScore"]["value"]
        incoherent_score = results["attributeScores"]["INCOHERENT"]["summaryScore"]["value"]

        return toxicity_score, spam_score, incoherent_score

    def calculate_risk_score(self, text):

        toxicity_score, spam_score, incoherent_score = self.analyze_text_with_perspective(text)

        if self.detect_phishing(text):
            return 100
        elif self.detect_spam(text):
            return round(100*spam_score)

        else:
            lexical_diversity_weight = 0.1
            flesch_reading_ease_weight = 0.1
            links_weight = 0.3 if len(self.included_urls(text)) else 0
            toxicity_score_weight = 0.1
            spam_score_weight = 0.3
            incoherent_score_weight = 0.1

            lexical_diversity_score = self.lexical_diversity(text)
            flesch_reading_ease_score = self.flesch_reading_ease(text)/100

            risk_score = (
                    lexical_diversity_score * lexical_diversity_weight +
                    flesch_reading_ease_score * flesch_reading_ease_weight +
                    links_weight +
                    toxicity_score * toxicity_score_weight +
                    spam_score * spam_score_weight +
                    incoherent_score * incoherent_score_weight
            )

            return round(risk_score*100)



#=================================================================================================================
email_analyzer = EmailAnalyzer('AIzaSyCrZnJ03Pz7gk5KtmK4U2Ks9s65gl6TI-o')

class SpamMail(FlaskForm):
    content = TextAreaField('Content', validators=[DataRequired(), Length(max=5000)])
    submit = SubmitField('Submit')

def extract_urls(text):
    url_pattern = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
    urls = re.findall(url_pattern, text)
    return urls

def spam_email_detector(content):
    host = "https://email-spam-detector.p.rapidapi.com/api/email_spam_detector"

    payload = {"text": content}

    headers = {
	"content-type": "application/json",
	"X-RapidAPI-Key": "2cfb47ebc9msh9fb2b632b70016dp1dad0ajsne31a2db9d539",
	"X-RapidAPI-Host": "email-spam-detector.p.rapidapi.com"
    }

    response = requests.post(host, json=payload, headers=headers)
    return response.json()

def malicious_url_detector(url):
    host = "https://exerra-phishing-check.p.rapidapi.com/"

    payload = {"url": url}

    headers = {
        "X-RapidAPI-Key": "2cfb47ebc9msh9fb2b632b70016dp1dad0ajsne31a2db9d539",
        "X-RapidAPI-Host": "exerra-phishing-check.p.rapidapi.com"
    }

    response = requests.get(host, headers=headers, params=payload)
    return response.json() 

def check_urls_with_safebrowsing(urls):
    api_key = 'AIzaSyDBLe1rxRBkhmhN37iqiI84dTMpbHS9EZc'
    s = SafeBrowsing(api_key)
    r = s.lookup_urls(urls)
    return r




def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/home')
@app.route('/')
def home():
    return render_template('Home_Page.html')


@app.route('/signuup')
def signuup():
    return render_template('Sign_Up_Page.html')

@app.route('/signin')
def signin():
    return render_template('Login_Page.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        # Find the user by email
        user = collection.find_one({'email': email})
        
        if user:
            # Verify the password using Argon2
            if argon2.verify(password, user['password']):
                session['user_id'] = str(user['_id'])
                return redirect(url_for('dashboard'))
            else:
                # Password does not match
                flash('Invalid username or password')
        else:
            # User not found
            flash('Invalid username or password')
    
    return render_template('Login_Page.html')


@app.route('/google-login')
def googleLogin():
    return oauth.Shieldmail.authorize_redirect(redirect_uri=url_for('googleCallback', _external=True))

@app.route('/signin-google')
def googleCallback():
    token = oauth.Shieldmail.authorize_access_token()
    print(token)
    if not token:
        flash("Failed to authenticate with Google.", "error")
        return redirect(url_for('signin'))
    
    email = token['userinfo']['email']
    user = collection.find_one({'email': email})
    current_year = datetime.now().year
    current_time = datetime.now()    
    current_time = datetime.now()

    last_login_year = current_time.year
    last_login_month = current_time.month
    last_login_day = current_time.day

    last_login = f"{last_login_year}-{last_login_month:02d}-{last_login_day:02d}"
    if user is None:
        user_data = {
            'email': email,
            'first_name': token['userinfo']['given_name'],
            'last_name': token['userinfo']['family_name'],
            'member_since': current_year,
            'last_login': last_login,
        }
        try:
            user_id = collection.insert_one(user_data).inserted_id
            user = collection.find_one({'_id': user_id})
        except Exception as e:
            flash("Error occurred while creating a new user: {}".format(str(e)), "error")
            return redirect(url_for('signin'))
    
    session['user_id'] = str(user['_id'])

    return redirect(url_for('dashboard'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        email = request.form['email']
        password = request.form['password']
        
        # Hash the password before storing it
        # Hash the password, using the default pbkdf2:sha256 method with a custom number of iterations
        hashed_password = argon2.hash(password)



        user_exists = collection.find_one({'email': email})
        if user_exists:
            return render_template('Sign_Up_Page.html', email_error='Email already exists.', first_name=first_name, last_name=last_name, email=email)
        
        current_year = datetime.now().year
        current_time = datetime.now().strftime('%Y-%m-%d')
        new_user_id = collection.insert_one({
            'email': email,
            'password': hashed_password,  # Store the hashed password here
            'first_name': first_name,
            'last_name': last_name,
            'member_since': current_year,
            'last_login': current_time
        }).inserted_id

        session['user_id'] = str(new_user_id)
        return redirect(url_for('dashboard'))
    
    return render_template('Sign_Up_Page.html')


#==============================================================================================================================================

@app.route('/dashboard')
@login_required
def dashboard():
    user_id = session['user_id']
    user = collection.find_one({"_id": ObjectId(user_id)})
    return render_template('User_Dashboard_Page.html', user=user)


@app.route('/profile')
@login_required
def profile():
    user_id = session['user_id']
    user = collection.find_one({"_id": ObjectId(user_id)})
    if user:
        user.pop('password', None)  
        return render_template('Profile_Info_Page.html', user=user)


@app.route('/emailcheck')
@login_required
def emailcheck():
    user_id = session['user_id']
    
    return render_template('Spam_Email_Page.html')

@app.route('/emailcheckbutton', methods=['POST'])
def emailcheckbutton():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401 

    if request.json:
        content = request.json.get('content', '')
        if not content:
            return jsonify({"error": "Please enter some content."}), 400

        # Check for URL presence
     #   if not re.search(r'https?:\/\/\S+', content):
      #      return jsonify({"error": "Please include at least one URL in the content."}), 400
        spam_result = spam_email_detector(content)
        pos_score = spam_result.get('sentiment', {}).get('POS', 0)
        is_spam_email = pos_score >= 0.8
        print("Spam detection result:", is_spam_email) 
         
        risk_score = email_analyzer.calculate_risk_score(content)
        phishing_detected = email_analyzer.detect_phishing(content)
        phishing_detected = True if phishing_detected == "yes" else False
        print(phishing_detected)
        spam_detected = email_analyzer.detect_spam(content)
        grammar_issues_count = email_analyzer.grammar_checker(content)
        lexical_diversity_score = email_analyzer.lexical_diversity(content)
        perspective=email_analyzer.analyze_text_with_perspective(content)
        reading=email_analyzer.flesch_reading_ease(content)
        incoherent_score = email_analyzer.incoherence_score(content)
        toxicity_score = email_analyzer.toxicity_score(content)
        Spam_Score = email_analyzer.spam_score(content)
        print(Spam_Score)

       

        extracted_urls = extract_urls(content)
        print(extracted_urls)

        urls_info = []

        for url in extracted_urls:
            url_result = malicious_url_detector(url)
            isMalicious = url_result.get('data').get('isScam',False)  
            urls_info.append({
                "url": url,
                "isMalicious": isMalicious,
            })
            
        
        urlsl=list()
        for i in urls_info:
            urlsl.append(i['url'])
            
        googlecheck= check_urls_with_safebrowsing(urlsl)
        malicious_link = False

        #for url, details in googlecheck.items():
         #   if details.get('malicious', False): 
          #        malicious_link = True
           #       break 
        malicious_values_url = any(malicious['isMalicious'] for malicious in urls_info)
        is_spam_url = malicious_values_url 
        

        urlsl=list()
        for i in urls_info:
            urlsl.append(i['url'])
                
        listx=list()
        listx.append([is_spam_email,malicious_link,is_spam_url,phishing_detected,spam_detected])
        final_result = any([is_spam_email, malicious_link, is_spam_url,phishing_detected,spam_detected])
        print(final_result)

        user_id = session.get('user_id')
        document_id = collection2.insert_one({
            "user_id": ObjectId(user_id),
            "content": content,
            "result": final_result,
            "urls": urlsl, 
            "risk_score": risk_score,
            "spam_detected": spam_detected,
            "phishing_detected": phishing_detected,
            "reading": spam_detected,
            "perspective": perspective,
            "date_checked": datetime.now().strftime('%Y-%m-%d'), 
            "incoherent_score": incoherent_score,
            "toxicity_score": toxicity_score, 
            "Spam_Score": Spam_Score,
            
        }).inserted_id

        response_message = 'The email content is considered spam.' if final_result else 'The email content is not considered spam.'
        
        response_data = {
        "result": final_result,
        "risk_score": risk_score,
        "grammar_issues_count": grammar_issues_count,
        "lexical_diversity_score": lexical_diversity_score,
        "reading": reading,
        "perspective":perspective,
        "spam_detected":spam_detected,
        "incoherent_score": incoherent_score,
        "toxicity_score": toxicity_score, 
        "Spam_Score": Spam_Score,
        "phishing_detected": phishing_detected,
    }
        
        return jsonify(response_data)

    return jsonify({"error": "Invalid request"}), 400

   
   
@app.route('/maliciouscheck')
@login_required
def maliciouscheck():
    user_id = session['user_id']
    return render_template('Malicious_Link_Page.html')        

@app.route('/maliciouslinkcheck', methods=['POST'])
@login_required
def check_malicious_link():
    if request.method == 'POST':
        user_id = session.get('user_id')
        data = request.get_json()
        malicious_link = data.get('link')  
        if not malicious_link:  # Check if the link is empty
                return jsonify({'error': 'Please enter a link to analyze.'}), 400
        url_result = malicious_url_detector(malicious_link)
        result = url_result.get('data', {}).get('isScam', False)
        collection1.insert_one({
            'user_id': ObjectId(user_id),
            'malicious_link': malicious_link,
            'isMalicious': result,
            'date_checked': datetime.now().strftime('%Y-%m-%d') 
        })

        return jsonify({'isMalicious': result})


@app.route('/MaliciousLinkChecks')
@login_required
def report_history():
    user_id = session['user_id']
    reports = collection1.find({"user_id": ObjectId(user_id)})
    reports_list = list(reports)
    
    for report in reports_list:
        date_checked_str = report['date_checked']
        date_checked_datetime = datetime.strptime(date_checked_str, '%Y-%m-%d')
        report['date_checked'] = date_checked_datetime.strftime('%d-%m-%Y')
    
    return render_template('Histo_link.html', reports=reports_list)

@app.route('/emailchecks')
@login_required
def report_historyy():
    user_id = session['user_id']
    reports = collection2.find({"user_id": ObjectId(user_id)})
    reports_list = list(reports)
    
    for report in reports_list:
        date_checked_str = report['date_checked']
        date_checked_datetime = datetime.strptime(date_checked_str, '%Y-%m-%d')
        report['date_checked'] = date_checked_datetime.strftime('%d-%m-%Y')
    
    return render_template('History_Page_Email.html', reports=reports_list)



@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('You have been logged out successfully.')
    return redirect(url_for('login'))


if __name__ == "__main__":
    app.run(host="0.0.0.0",debug=True)
