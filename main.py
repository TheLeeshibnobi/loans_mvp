from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from overview_metrics import OverviewMetrics
from dotenv import load_dotenv
from charts import Charts
from registration import Registration
from borrower_information import BorrowerInformation
from loans import Loans
import os
from flask_wtf.csrf import CSRFProtect, generate_csrf
from user_authentication import UserAuthentication
from customer_analytics import CustomerAnalytics
from datetime import datetime
from business_analytics import BusinessAnalytics
from capital_functions import CapitalFunctions
from settings import Settings
import traceback
from repayment import Repayment
from expenses import Expenses
from subscription import Subscriptions


from dotenv import load_dotenv
load_dotenv()
import secrets
print(secrets.token_hex(16))




app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')
csrf = CSRFProtect(app)

from datetime import datetime

def datetimeformat(value):
    try:
        return datetime.fromisoformat(value).strftime('%d %b %Y')
    except Exception:
        return value

app.jinja_env.filters['datetimeformat'] = datetimeformat

@app.context_processor
def inject_csrf_token():
    return dict(csrf_token=generate_csrf())


@app.route('/')
def user_auth():
    return render_template('user_login_signup.html')


@app.route('/business_login', methods=['GET', 'POST'])
def business_login():
    if request.method == 'GET':
        return render_template("user_login_signup.html")

    # Handle POST request
    business_email = request.form.get('business_email')
    business_password = request.form.get('business_password')

    auth = UserAuthentication()

    try:
        result = auth.business_login(business_email, business_password)

        if result.get("success", False):
            business_data = result.get('business_data', {})
            business_id = business_data.get('id')

            subscription_tool = Subscriptions()

            # Check if business has paid
            if not subscription_tool.check_business_pay_status(business_id):
                # Store business data in session for subscription flow
                session['pending_business_data'] = business_data
                session['business_data'] = business_data  # Also store here to avoid session expired errors
                flash('Please complete your subscription to access the dashboard.', 'warning')
                return redirect(url_for('subscription'))

            # Business has paid, proceed with normal login
            session['business_data'] = business_data
            # Clean up any pending data from previous sessions
            session.pop('pending_business_data', None)
            flash('Business login successful!', 'success')

            # redirects for the user to now login into that business
            return redirect(url_for('login'))
        else:
            flash('Wrong business credentials', 'error')
            return render_template("user_login_signup.html")

    except Exception as e:
        print(f'Exception: {e}')
        flash('An error occurred during business login', 'error')
        return render_template("user_login_signup.html")


@app.route('/subscription', methods=['GET', 'POST'])
def subscription():
    """Handle subscription page and payment processing"""

    # Get business data from session - check both locations
    business_data = session.get('business_data') or session.get('pending_business_data')

    if not business_data:
        flash('Business session expired. Please log into business first', 'error')
        return redirect(url_for('business_login'))

    business_id = business_data.get('id')

    if not business_id:
        flash('Business ID not found in session', 'error')
        return redirect(url_for('business_login'))

    if request.method == 'GET':
        # Display the subscription page
        return render_template('subscription.html')

    elif request.method == 'POST':
        try:
            # Get and validate form data
            first_name = request.form.get('firstName')
            last_name = request.form.get('lastName')
            email = request.form.get('email')
            phone = request.form.get('phone')
            plan = request.form.get('plan')
            amount = request.form.get('amount')

            if not all([first_name, last_name, email, phone, plan, amount]):
                flash('All fields are required.', 'error')
                return render_template('subscription.html')

            # Clean amount
            import re
            amount_clean = re.sub(r'[^\d.]', '', amount)
            if not amount_clean:
                flash('Invalid amount format.', 'error')
                return render_template('subscription.html')

            # Handle payment
            subscription_tool = Subscriptions()
            result = subscription_tool.buy_plan(
                business_id=business_id,
                amount=float(amount_clean),
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone,
                plan=plan
            )

            if result:
                # Payment succeeded - now store the business data properly
                session['business_data'] = business_data  # Move from pending to active
                session.pop('pending_business_data', None)  # Clean up pending data

                session['subscription_data'] = {
                    'plan': plan,
                    'amount': amount,
                    'email': email,
                    'first_name': first_name,
                    'last_name': last_name,
                    'business_data': business_data
                }

                flash('Payment request sent successfully! Please check your phone for the mobile money prompt.',
                      'success')
                return redirect(url_for('subscription_success'))
            else:
                # Payment failed or timed out
                flash('Payment was not completed or timed out. Please try again.', 'error')
                return render_template('subscription.html')

        except Exception as e:
            print(f'Subscription error: {e}')
            flash('An error occurred while processing your request. Please try again.', 'error')
            return render_template('subscription.html')


@app.route('/subscription-success')
def subscription_success():
    """Display subscription success page"""
    subscription_data = session.get('subscription_data')
    if not subscription_data:
        flash('No subscription data found.', 'error')
        return redirect(url_for('business_login'))

    # You can use the success template we created earlier
    # Just make sure to pass the subscription data to it
    return render_template('paid_successfully.html', data=subscription_data)




@app.route('/business_signup', methods=['POST', 'GET'])
def business_signup():
    if request.method == 'GET':
        return render_template("user_login_signup.html")

    auth = UserAuthentication()
    business_name = request.form.get('business_name')
    email = request.form.get('business_email')
    password = request.form.get('business_password')

    try:
        admin_key = auth.business_signup(business_name, email, password)
        if admin_key:  # Now returns the admin key instead of boolean
            flash(f'{business_name} signed up as business successfully!', 'success')
            return render_template("user_login_signup.html",
                                 show_admin_key=True,
                                 admin_key=admin_key)
        else:
            flash(f'Error signing up {business_name}', 'error')
            return render_template("user_login_signup.html")
    except Exception as e:
        print(f'Exception: {e}')
        flash('An error occurred during business signup', 'error')
        return render_template("user_login_signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    # Check if business is logged in at the start
    if 'business_data' not in session:
        flash('Please log into business first', 'error')
        return redirect(url_for('business_login'))

    if request.method == "GET":
        return render_template("user_login_signup.html",
                               show_user_login=True,
                               business_name=session['business_data'].get('name'))

    # Handle POST request
    auth = UserAuthentication()
    email = request.form["email"]
    password = request.form["password"]
    response = auth.login(email, password)

    if response.get("success", False):
        flash("Login successful!", "success")
        return redirect(url_for("overview_dashboard"))
    else:
        flash(f"Login failed: {response.get('message', 'Invalid credentials')}", "error")
        return redirect(url_for("login"))


@app.route("/signup", methods=['GET', 'POST'])
def signup():
    auth = UserAuthentication()

    if request.method == 'POST':
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]
        secret_key = request.form["secret_key"]

        response = auth.sign_up(name, email, password, secret_key)

        # Check if signup was successful
        if response.get("success", False):
            flash("Sign up successful! You can now log in.", "success")
            return redirect(url_for("login"))
        else:
            # Check if it's a secret key error or general failure
            if "secret" in response.get("message", "").lower():
                flash("Account creation failed: Invalid secret key.", "error")
            else:
                flash(f"Account creation failed: {response.get('message', 'Unknown error')}", "error")

            # Stay on the same page to show the error
            return render_template("user_login_signup.html")

    # Handle GET request - render the signup page
    return render_template("user_login_signup.html")

@app.route('/business_forgot_password', methods=['POST', 'GET'])
def business_forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        print(email)

        auth_tool = UserAuthentication()
        try:
            result = auth_tool.email_retrieved_business_password(email)
            if not result:
                flash('FAILED TO SEND PASSWORD', 'error')
                return redirect(url_for('business_login'))  # Changed this line

            flash('PASSWORD SENT TO YOUR EMAIL SUCCESSFULLY', 'success')
            return redirect(url_for('business_login'))

        except Exception as e:
            print(f'Exception: {e}')
            flash('An error occurred. Please try again.', 'error')
            return redirect(url_for('business_login'))

    # Handle GET request (if someone accesses the URL directly)
    return redirect(url_for('business_login'))

@app.route('/user_forgot_password', methods=['POST', 'GET'])
def user_forgot_password():
    # Get business_id from session
    if 'business_data' not in session:
        flash('Business session expired. Please log into business first', 'error')
        return redirect(url_for('business_login'))

    business_id = session['business_data'].get('id')

    if not business_id:
        flash('Business ID not found in session', 'error')
        return redirect(url_for('business_login'))

    if request.method == 'POST':
        email = request.form.get('email')

        auth_tool = UserAuthentication()
        try:
            result = auth_tool.email_retrieved_user_password(business_id, email)
            if not result:
                flash('FAILED TO SEND PASSWORD', 'error')
                return redirect(url_for('business_login'))  # Changed this line

            flash('PASSWORD SENT TO YOUR EMAIL SUCCESSFULLY', 'success')
            return redirect(url_for('business_login'))

        except Exception as e:
            print(f'Exception: {e}')
            flash('An error occurred. Please try again.', 'error')
            return redirect(url_for('business_login'))

    # Handle GET request (if someone accesses the URL directly)
    return redirect(url_for('business_login'))



@app.route('/unauthorized_access')
def unauthorized_access():

    return render_template('unauthorized_access.html')


@app.route('/overview_dashboard', methods=['GET', 'POST'])
def overview_dashboard():
    # Get business_id from session
    if 'business_data' not in session:
        flash('Business session expired. Please log into business first', 'error')
        return redirect(url_for('business_login'))

    business_id = session['business_data'].get('id')

    if not business_id:
        flash('Business ID not found in session', 'error')
        return redirect(url_for('business_login'))

    loan_tool = Loans()
    loan_tool.update_overdue_loans(business_id)

    if request.method == 'POST':
        data = request.get_json()
        if not data or data.get('action') != 'update_period':
            return jsonify({'success': False, 'error': 'Invalid request'}), 400

        selected_period = data.get('period', 'Last 30 Days')
        overview_tool = OverviewMetrics()
        chart_tool = Charts()

        try:
            response_data = {
                'success': True,
                'total_disbursed': f"ZMK {overview_tool.total_disbursed(selected_period, business_id):,.2f}",
                'total_repaid': f"ZMK {overview_tool.total_repaid(selected_period, business_id):,.2f}",
                'outstanding_balance': f"ZMK {overview_tool.outstanding_balance(selected_period, business_id):,.2f}",
                'expected_interest': f"ZMK {overview_tool.expected_interest(selected_period, business_id):,.2f}",
                'average_loan_size': f"ZMK {overview_tool.average_loan_size(selected_period, business_id):,.2f}",
                'average_duration': f"{overview_tool.average_duration(selected_period, business_id):,.0f} days",
                'active_loans': f"{overview_tool.active_loans(selected_period, business_id):,}",
                'default_rate': f"{overview_tool.default_rate(selected_period, business_id)}%",
                'transaction_costs': f"ZMK{overview_tool.total_transaction_costs(selected_period, business_id)}",
                'discount_costs': f"ZMK{overview_tool.total_discounts_given(selected_period, business_id)}",
                 'expense_costs' : f"ZMK{overview_tool.total_period_expenses(selected_period, business_id)}",

                'available_cash': overview_tool.available_cash(business_id),
                'gender_chart': chart_tool.borrowers_by_gender(selected_period),
                # Assuming Charts class also needs updating
                'status_distribution_chart': chart_tool.loan_status_distribution(selected_period)
                # Assuming Charts class also needs updating
            }
            return jsonify(response_data)
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    # Existing GET route logic
    selected_period = request.args.get('period', 'Last 30 Days')
    overview_tool = OverviewMetrics()
    chart_tool = Charts()

    available_cash = overview_tool.available_cash(business_id)
    total_disbursed = f"ZMK {overview_tool.total_disbursed(selected_period, business_id):,.2f}"
    total_repaid = f"ZMK {overview_tool.total_repaid(selected_period, business_id):,.2f}"
    outstanding_balance = f"ZMK {overview_tool.outstanding_balance(selected_period, business_id):,.2f}"
    expected_interest = f"ZMK {overview_tool.expected_interest(selected_period, business_id):,.2f}"
    average_loan_size = f"ZMK {overview_tool.average_loan_size(selected_period, business_id):,.2f}"
    average_duration = f"{overview_tool.average_duration(selected_period, business_id):,.0f} days"
    active_loans = f"{overview_tool.active_loans(selected_period, business_id):,}"
    default_rate = f"{overview_tool.default_rate(selected_period, business_id)}%"
    transaction_costs = f"ZMK{overview_tool.total_transaction_costs(selected_period, business_id)}"
    discount_costs = f"ZMK{overview_tool.total_discounts_given(selected_period, business_id)}"
    expense_costs = f"ZMK{overview_tool.total_period_expenses(selected_period, business_id)}"

    recent_borrowers = overview_tool.recent_borrowers(business_id)
    location_summary = overview_tool.borrowers_by_location(selected_period, business_id)
    weekly_loans_due = overview_tool.weekly_loans_due(business_id)
    gender_chart = chart_tool.borrowers_by_gender(selected_period)  # May need business_id parameter
    status_distribution_chart = chart_tool.loan_status_distribution(selected_period)  # May need business_id parameter

    formatted_cash = f"{available_cash:,.2f}"

    return render_template('overview.html',
                           available_cash=formatted_cash,
                           selected_period=selected_period,
                           total_disbursed=total_disbursed,
                           total_repaid=total_repaid,
                           outstanding_balance=outstanding_balance,
                           expected_interest=expected_interest,
                           average_loan_size=average_loan_size,
                           average_duration=average_duration,
                           active_loans=active_loans,
                           default_rate=default_rate,
                           discount_costs=discount_costs,
                           expense_costs = expense_costs,
                           transaction_costs=transaction_costs,
                           gender_chart=gender_chart,
                           status_distribution_chart=status_distribution_chart,
                           recent_borrowers=recent_borrowers,
                           location_summary=location_summary,
                           weekly_loans_due=weekly_loans_due)


@app.route('/loans_data', methods=['POST', 'GET'])
def loans_data():
    # Get business_id from session
    if 'business_data' not in session:
        flash('Business session expired. Please log into business first', 'error')
        return redirect(url_for('business_login'))

    business_id = session['business_data'].get('id')

    if not business_id:
        flash('Business ID not found in session', 'error')
        return redirect(url_for('business_login'))

    loans_tool = Loans()
    overview_tool = OverviewMetrics()

    from_date = request.args.get('start_date')
    to_date = request.args.get('end_date')
    loan_type = request.args.get('loan_type')

    # Since form method is GET, get search query from request.args
    search_query = request.args.get('query')

    if from_date or to_date or loan_type:
        # Note: You'll need to update the Loans.filtered_loans() method to accept business_id
        loans = loans_tool.filtered_loans(business_id, from_date, to_date, loan_type)
    elif search_query:
        # Note: You'll need to update the Loans.search_by_id() method to accept business_id
        loans = loans_tool.search_by_id(business_id, search_query)
    else:
        loans = overview_tool.recent_borrowers(business_id)

    return render_template('loans_data.html', loans=loans)


@app.route('/download_loans_csv', methods=['POST', 'GET'])
def download_loans_csv():
    # Get business_id from session
    if 'business_data' not in session:
        flash('Business session expired. Please log into business first', 'error')
        return redirect(url_for('business_login'))

    business_id = session['business_data'].get('id')

    if not business_id:
        flash('Business ID not found in session', 'error')
        return redirect(url_for('business_login'))

    loans_tool = Loans()
    start_date = request.form.get('download_start_date')
    end_date = request.form.get('download_end_date')

    try:
        # Note: You'll need to update the Loans.download_csv() method to accept business_id
        return loans_tool.download_csv(business_id, start_date, end_date)
    except Exception as e:
        print(f'Exception: {e}')
        flash(f'Error: {e}')
        return redirect(request.referrer)


@app.route('/search_borrower', methods=['GET', 'POST'])
def search_borrower():
    # Get business_id from session
    if 'business_data' not in session:
        flash('Business session expired. Please log into business first', 'error')
        return redirect(url_for('business_login'))

    business_id = session['business_data'].get('id')

    if not business_id:
        flash('Business ID not found in session', 'error')
        return redirect(url_for('business_login'))

    # Check if this is a search request (has nrc_search parameter)
    nrc_number = request.args.get('nrc_search')

    if nrc_number:
        # User has submitted a search, get the borrower data
        registration_tool = Registration()
        # Note: You'll need to update the Registration.get_borrower_id() method to accept business_id
        borrower_data = registration_tool.get_borrower_id(nrc=nrc_number, business_id=business_id)

        # Return the results template
        return render_template('borrower_results.html', borrower_data=borrower_data)
    else:
        # No search parameter, show the search form
        return render_template('search_borrower.html')


@app.route('/borrower_information')
def borrower_information():
    # Get business_id from session
    if 'business_data' not in session:
        flash('Business session expired. Please log into business first', 'error')
        return redirect(url_for('business_login'))

    business_id = session['business_data'].get('id')

    if not business_id:
        flash('Business ID not found in session', 'error')
        return redirect(url_for('business_login'))

    borrower_id = request.args.get('borrower_id')

    if not borrower_id:
        flash('Borrower ID is required', 'error')
        return redirect(url_for('search_borrower'))

    # get the loan_id using the borrower id
    registration_tool = Registration()
    # Note: You'll need to update these Registration methods to accept business_id
    loan_id = registration_tool.get_loan_id(borrower_id, business_id)
    borrower_data = registration_tool.get_borrower_data(borrower_id, business_id)

    # Verify that the borrower belongs to this business
    if not borrower_data:
        flash('Borrower not found or does not belong to your business', 'error')
        return redirect(url_for('search_borrower'))

    borrower_information_tool = BorrowerInformation()

    # Note: You'll need to update these BorrowerInformation methods to accept business_id
    payment_history = borrower_information_tool.get_borrower_payment_history(loan_id, business_id)
    outstanding_debts = borrower_information_tool.total_outstanding_debts(borrower_id, business_id)
    default_assessment = borrower_information_tool.default_risk_assessment(borrower_id, business_id)
    credit_status = borrower_information_tool.account_status(borrower_id, business_id)
    recent_borrower_history = borrower_information_tool.recent_borrower_history(borrower_id, business_id)

    return render_template(
        'borrower_information.html',
        borrower_data=borrower_data,
        payment_history=payment_history,
        outstanding_debts=outstanding_debts,
        default_assessment=default_assessment,
        credit_status=credit_status,
        recent_borrower_history=recent_borrower_history
    )


@app.route('/borrower_data', methods=['POST', 'GET'])
def borrower_data():
    # Get business_id from session
    if 'business_data' not in session:
        flash('Business session expired. Please log into business first', 'error')
        return redirect(url_for('business_login'))

    business_id = session['business_data'].get('id')

    if not business_id:
        flash('Business ID not found in session', 'error')
        return redirect(url_for('business_login'))

    borrower_tool = BorrowerInformation()
    # Note: You'll need to update the BorrowerInformation.get_borrowers() method to accept business_id
    borrowers = borrower_tool.get_borrowers(business_id)

    return render_template('borrowers_data.html', borrowers=borrowers)


@app.route('/loan_form')
def loan_form():
    """Display the loan form"""
    if session.get("user", {}).get("role") != "admin":
        # Block access
        flash("Access denied: Admins only.", "error")
        return render_template('unauthorized_access.html')

    # Get business_id from session
    if 'business_data' not in session:
        flash('Business session expired. Please log into business first', 'error')
        return redirect(url_for('business_login'))

    business_id = session['business_data'].get('id')

    if not business_id:
        flash('Business ID not found in session', 'error')
        return redirect(url_for('business_login'))

    borrower_id = request.args.get('borrower_id')

    if not borrower_id:
        flash('Borrower ID is required', 'error')
        return redirect(url_for('search_borrower'))

    loan_tool = Loans()
    # Note: You'll need to update the Loans.borrower_identity() method to accept business_id
    borrower_identity = loan_tool.borrower_identity(borrower_id, business_id)

    return render_template(
        'loan_form.html',
        borrower_identity=borrower_identity,
        borrower_id=borrower_id  # Pass borrower_id to template
    )


@app.route('/register_borrower', methods=['GET', 'POST'])
def register_borrower():
    if session.get("user", {}).get("role") != "admin":
        # Block access
        flash("Access denied: Admins only.", "error")
        return render_template('unauthorized_access.html')

    # Get business_id from session
    if 'business_data' not in session:
        flash('Business session expired. Please log into business first', 'error')
        return redirect(url_for('business_login'))

    business_id = session['business_data'].get('id')

    if not business_id:
        flash('Business ID not found in session', 'error')
        return redirect(url_for('business_login'))

    if request.method == 'GET':
        return render_template('register_new_borrower.html')

    elif request.method == 'POST':
        # Get form data using request.form
        name = request.form.get('name')
        gender = request.form.get('gender')
        location = request.form.get('location')
        nrc_number = request.form.get('nrc_number')
        mobile = request.form.get('mobile')
        occupation = request.form.get('occupation')
        birth_date = request.form.get('birth_date')
        notes = request.form.get('notes')

        # Call your function
        registration_tool = Registration()
        # Note: You'll need to update the Registration.register_new_borrower() method to accept business_id
        result = registration_tool.register_new_borrower(
            name=name,
            gender=gender,
            location=location,
            nrc_number=nrc_number,
            mobile=mobile,
            occupation=occupation,
            birth_date=birth_date,
            notes=notes,
            business_id=business_id
        )

        if result:
            flash('Borrower registered successfully!', 'success')
            return render_template(
                'successful_borrower_submitted.html',
                borrower_name=name,
                nrc_number=nrc_number,
                mobile=mobile,
                location=location
            )
        else:
            flash('Error registering borrower. Please try again.', 'error')

        return redirect(url_for('register_borrower'))


@app.route('/submit-loan', methods=['POST'])
def submit_loan():
    """Handle loan form submission with enhanced debugging"""
    if session.get("user", {}).get("role") != "admin":
        flash("Access denied: Admins only.", "error")
        return render_template('unauthorized_access.html')

    # Get business_id from session
    if 'business_data' not in session:
        flash('Business session expired. Please log into business first', 'error')
        return redirect(url_for('business_login'))

    business_id = session['business_data'].get('id')

    if not business_id:
        flash('Business ID not found in session', 'error')
        return redirect(url_for('business_login'))

    try:
        # FIRST: Debug raw form data before processing
        print("=== RAW FORM DATA DEBUG ===")
        print("All form data:")
        for key, value in request.form.items():
            print(f"  {key}: '{value}' (type: {type(value)})")

        print("\nAll files:")
        for key, file in request.files.items():
            if hasattr(file, 'filename'):
                print(f"  {key}: {file.filename} (type: {type(file)})")
            else:
                print(f"  {key}: {file} (type: {type(file)})")

        # Get form data
        borrower_id = request.form.get('borrower_id')
        amount = float(request.form.get('amount', 0))
        transaction_costs = float(request.form.get('transaction_costs', 0))
        interest_rate = float(request.form.get('interest_rate', 0))
        duration_days = int(request.form.get('duration_days', 0))
        due_date = request.form.get('due_date')
        loan_reason = request.form.get('loan_reason')

        # Handle file uploads
        contract_file = request.files.get('contract_file')
        collateral_images = request.files.getlist('collateral_images')

        # Check if collateral_images is empty
        print(f"\nCollateral images details:")
        print(f"  Count: {len(collateral_images)}")
        for i, img in enumerate(collateral_images):
            if hasattr(img, 'filename') and img.filename:
                # Only read size if file has content
                try:
                    current_pos = img.tell() if hasattr(img, 'tell') else 0
                    img.seek(0, 2)  # Seek to end
                    size = img.tell()
                    img.seek(current_pos)  # Reset to original position
                    print(f"  Image {i}: filename='{img.filename}', size={size}")
                except:
                    print(f"  Image {i}: filename='{img.filename}', size=unknown")
            else:
                print(f"  Image {i}: empty file")

        # Specific checks for common issues
        print("\n=== POTENTIAL ISSUES CHECK ===")

        # Check if borrower_id is actually coming through
        if not request.form.get('borrower_id'):
            print("❌ CRITICAL: borrower_id is missing from form data!")
        else:
            print(f"✓ borrower_id found: {request.form.get('borrower_id')}")

        # Check if amount is valid
        try:
            amount_raw = request.form.get('amount', 0)
            amount_float = float(amount_raw)
            if amount_float <= 0:
                print(f"❌ CRITICAL: Amount is <= 0: {amount_float}")
            else:
                print(f"✓ Amount is valid: {amount_float}")
        except ValueError as e:
            print(f"❌ CRITICAL: Amount conversion failed: {e}")

        # Check if interest_rate is valid
        try:
            interest_raw = request.form.get('interest_rate', 0)
            interest_float = float(interest_raw)
            if interest_float < 0:
                print(f"❌ CRITICAL: Interest rate is < 0: {interest_float}")
            else:
                print(f"✓ Interest rate is valid: {interest_float}")
        except ValueError as e:
            print(f"❌ CRITICAL: Interest rate conversion failed: {e}")

        # Check if duration_days is valid
        try:
            duration_raw = request.form.get('duration_days', 0)
            duration_int = int(duration_raw)
            if duration_int <= 0:
                print(f"❌ CRITICAL: Duration is <= 0: {duration_int}")
            else:
                print(f"✓ Duration is valid: {duration_int}")
        except ValueError as e:
            print(f"❌ CRITICAL: Duration conversion failed: {e}")

        # Check due_date
        due_date_raw = request.form.get('due_date')
        if not due_date_raw:
            print("❌ CRITICAL: Due date is missing!")
        else:
            print(f"✓ Due date found: {due_date_raw}")

        # Check contract file
        contract_file_check = request.files.get('contract_file')
        if not contract_file_check or contract_file_check.filename == '':
            print("❌ CRITICAL: Contract file is missing!")
        else:
            print(f"✓ Contract file found: {contract_file_check.filename}")

        # Check loan reason
        loan_reason_raw = request.form.get('loan_reason')
        if not loan_reason_raw:
            print("❌ CRITICAL: Loan reason is missing!")
        else:
            print(f"✓ Loan reason found: {loan_reason_raw}")

        print("=== END FORM VALIDATION CHECK ===\n")

        # Enhanced debug prints
        print(f"=== DETAILED LOAN SUBMISSION DEBUG ===")
        print(f"business_id: {business_id} (type: {type(business_id)})")
        print(f"borrower_id: {borrower_id} (type: {type(borrower_id)})")
        print(f"amount: {amount} (type: {type(amount)})")
        print(f"transaction_costs: {transaction_costs} (type: {type(transaction_costs)})")
        print(f"interest_rate: {interest_rate} (type: {type(interest_rate)})")
        print(f"duration_days: {duration_days} (type: {type(duration_days)})")
        print(f"due_date: {due_date} (type: {type(due_date)})")
        print(f"loan_reason: {loan_reason}")
        print(f"contract_file: {contract_file}")
        print(f"contract_file.filename: {contract_file.filename if contract_file else 'None'}")
        print(f"collateral_images count: {len(collateral_images) if collateral_images else 0}")

        # Validate required fields BEFORE calling the method
        missing_fields = []
        if not borrower_id:
            missing_fields.append("borrower_id")
        if not amount or amount <= 0:
            missing_fields.append("amount (must be > 0)")
        if interest_rate is None or interest_rate < 0:
            missing_fields.append("interest_rate (must be >= 0)")
        if not duration_days or duration_days <= 0:
            missing_fields.append("duration_days (must be > 0)")
        if not due_date:
            missing_fields.append("due_date")
        if not loan_reason:
            missing_fields.append("loan_reason")

        if missing_fields:
            print(f"ERROR: Missing/invalid required fields: {missing_fields}")
            flash(f'Invalid fields: {", ".join(missing_fields)}', 'error')
            return redirect(url_for('loan_form', borrower_id=borrower_id))

        if not contract_file or contract_file.filename == '':
            print("ERROR: Missing contract file")
            flash('Contract file is required', 'error')
            return redirect(url_for('loan_form', borrower_id=borrower_id))

        print("All validations passed, creating Loans instance...")

        # Submit loan with detailed error checking
        loan_tool = Loans()

        # First, let's verify the borrower exists
        print(f"Checking if borrower {borrower_id} exists for business {business_id}...")
        try:
            borrower_check = loan_tool.borrower_identity(borrower_id, business_id)
            print(f"Borrower check result: {borrower_check}")
            if borrower_check.get('name') == 'Unknown':
                print(f"ERROR: Borrower {borrower_id} not found for business {business_id}")
                flash(f'Borrower with ID {borrower_id} not found for this business', 'error')
                return redirect(url_for('loan_form', borrower_id=borrower_id))
        except Exception as borrower_error:
            print(f"ERROR checking borrower: {borrower_error}")
            flash('Error verifying borrower. Please try again.', 'error')
            return redirect(url_for('loan_form', borrower_id=borrower_id))

        print("Borrower verified, calling old_borrower_loan method...")

        # Filter out empty collateral images
        valid_collateral_images = [img for img in collateral_images if img.filename]
        print(f"Valid collateral images: {len(valid_collateral_images)}")

        loan_id = loan_tool.old_borrower_loan(
            borrower_id=borrower_id,
            business_id=business_id,
            amount=amount,
            transaction_costs=transaction_costs,
            interest_rate=interest_rate,
            duration_days=duration_days,
            due_date=due_date,
            loan_reason=loan_reason,
            contract_file_obj=contract_file,
            collateral_files_list=valid_collateral_images if valid_collateral_images else None
        )

        print(f"=== LOAN SUBMISSION RESULT ===")
        print(f"loan_id returned: {loan_id} (type: {type(loan_id)})")

        if loan_id:
            print("SUCCESS: Loan submitted successfully")
            flash('Loan application submitted successfully!', 'success')

            template_vars = {
                'borrower_id': borrower_id,
                'loan_id': loan_id,
                'loan_amount': amount,
                'loan_duration': duration_days,
                'interest_rate': interest_rate,
                'due_date': due_date
            }
            print(f"Template variables: {template_vars}")

            return render_template('successful_loan_submitted.html', **template_vars)
        else:
            print("ERROR: Loan submission failed - loan_id is None")
            print("This means one of the following failed:")
            print("1. Input validation in old_borrower_loan method")
            print("2. Borrower verification")
            print("3. File upload")
            print("4. Database insertion")
            print("Check the logs above for specific error messages")

            flash('Error submitting loan application. Please check all fields and try again.', 'error')
            return redirect(url_for('loan_form', borrower_id=borrower_id))

    except ValueError as e:
        print(f"ValueError in submit_loan: {e}")
        import traceback
        traceback.print_exc()
        flash('Invalid input values. Please check your entries.', 'error')
        return redirect(url_for('loan_form', borrower_id=borrower_id))
    except Exception as e:
        print(f"CRITICAL ERROR in submit_loan: {e}")
        import traceback
        traceback.print_exc()
        flash('An unexpected error occurred. Please try again.', 'error')
        return redirect(url_for('loan_form', borrower_id=borrower_id))


@app.route('/customer_analytics_dashboard', methods=['POST', 'GET'])
def customer_analytics_dashboard():
    # Get business_id from session
    if 'business_data' not in session:
        flash('Business session expired. Please log into business first', 'error')
        return redirect(url_for('business_login'))

    business_id = session['business_data'].get('id')

    if not business_id:
        flash('Business ID not found in session', 'error')
        return redirect(url_for('business_login'))

    try:
        # Get form data with proper error handling
        gender = request.form.get('gender')
        month = request.form.get('months')
        year_str = request.form.get('year')

        # Debug: Print what we're getting from the form
        print(f"Debug - Business ID: {business_id}")
        print(f"Debug - Gender: {gender}, Month: {month}, Year: {year_str}")
        print(f"Debug - All form data: {dict(request.form)}")

        # Validate and convert year
        if year_str is None or year_str == '':
            # Provide default year or handle the error
            year = datetime.now().year  # Use current year as default
            print(f"Warning: No year provided, using default: {year}")
        else:
            try:
                year = int(year_str)
            except (ValueError, TypeError) as e:
                print(f"Error converting year to int: {e}")
                year = datetime.now().year  # Use current year as fallback
                print(f"Using fallback year: {year}")

        # Validate other required fields
        if gender is None:
            gender = "All"  # Default value
        if month is None:
            month = "All Months"  # Default value

        print(f"Final values - Business ID: {business_id}, Gender: {gender}, Month: {month}, Year: {year}")

        # Initialize analytics tool
        customer_analytics_tool = CustomerAnalytics()

        # kpi cards data variables - Note: You'll need to update all these methods to accept business_id
        total_customers = customer_analytics_tool.total_customers(gender, month, year, business_id)
        best_location = customer_analytics_tool.best_location(gender, year, month, business_id)
        worst_location = customer_analytics_tool.worst_location(gender, year, month, business_id)
        average_amount = customer_analytics_tool.average_loan_amount(gender, year, month, business_id)

        # chart variables - Note: You'll need to update all these methods to accept business_id
        loans_location_chart = customer_analytics_tool.loans_by_location_chart(gender, year, month, business_id)
        loans_occupation_chart = customer_analytics_tool.loans_by_occupation_chart(gender, year, month, business_id)
        age_group_chart = customer_analytics_tool.age_group_radial_bar_chart(gender, year, month, business_id)

        # location performance kpi cards - Note: You'll need to update this method to accept business_id
        location_scores = customer_analytics_tool.location_performance_ranking(gender, year, month, business_id)

        return render_template(
            'customer_analytics.html',
            total_customers=total_customers,
            best_location=best_location,
            worst_location=worst_location,
            average_amount=average_amount,
            selected_gender=gender,  # Preserve form state
            selected_month=month,
            selected_year=year,
            borrower_id=request.form.get('borrower_id'),  # Optional

            loans_location_chart=loans_location_chart,
            loans_occupation_chart=loans_occupation_chart,
            age_group_chart=age_group_chart,

            location_scores=location_scores
        )

    except Exception as e:
        # Log the full error for debugging
        print(f"Error in customer_analytics_dashboard: {e}")
        import traceback
        traceback.print_exc()

        # Return error page or default values
        return render_template(
            'customer_analytics.html',
            error_message=f"An error occurred: {str(e)}",
            total_customers=0,
            best_location="Error",
            worst_location="Error",
            average_amount=0.0
        )


@app.route('/business_analytics_dashboard', methods=['POST', 'GET'])
def business_analytics():
    try:
        # Get business_id from session
        if 'business_data' not in session:
            flash('Business session expired. Please log into business first', 'error')
            return redirect(url_for('business_login'))

        business_id = session['business_data'].get('id')

        if not business_id:
            flash('Business ID not found in session', 'error')
            return redirect(url_for('business_login'))

        # Get form data with proper error handling
        gender = request.form.get('gender')
        month = request.form.get('months')
        year_str = request.form.get('year')
        loan_reason = request.form.get('loan_reason')

        # Debug: Print what we're getting from the form
        print(f"Debug - Gender: {gender}, Month: {month}, Year: {year_str}, Loan Reason: {loan_reason}")
        print(f"Debug - Business ID: {business_id}")
        print(f"Debug - All form data: {dict(request.form)}")

        # Validate and convert year
        if year_str is None or year_str == '':
            # Provide default year or handle the error
            year = datetime.now().year  # Use current year as default
            print(f"Warning: No year provided, using default: {year}")
        else:
            try:
                year = int(year_str)
            except (ValueError, TypeError) as e:
                print(f"Error converting year to int: {e}")
                year = datetime.now().year  # Use current year as fallback
                print(f"Using fallback year: {year}")

        # Validate other required fields
        if gender is None:
            gender = "All"  # Default value
        if month is None:
            month = "All Months"  # Default value

        print(f"Final values - Gender: {gender}, Month: {month}, Year: {year}, Loan Reason: {loan_reason}, Business ID: {business_id}")

        business_analytics_tool = BusinessAnalytics()

        # Pass business_id to all method calls
        total_loans_issued = business_analytics_tool.total_loans_issued(gender, month, year, business_id)
        revenue_generated = business_analytics_tool.total_revenue_generated(gender, month, year, business_id)
        default_rate = business_analytics_tool.default_rate(gender, month, year, business_id)
        active_portfolio = business_analytics_tool.active_portfolio(gender, month, year, business_id)

        # Only generate chart if loan_reason is provided
        loan_reason_trend_chart = None
        if loan_reason:
            loan_reason_trend_chart = business_analytics_tool.loan_reason_trend_chart(gender, year, loan_reason, business_id)

        interest_vs_transaction_costs_chart = business_analytics_tool.interest_vs_transaction_costs_chart(gender, year, business_id)
        loan_repayments_vs_discount_chart = business_analytics_tool.loan_repayments_vs_discount_chart(gender, year, business_id)

        return render_template(
            'business_analytics.html',
            total_loans_issued=total_loans_issued,
            revenue_generated=revenue_generated,
            default_rate=default_rate,
            active_portfolio=active_portfolio,
            loan_reason_trend_chart=loan_reason_trend_chart,
            interest_vs_transaction_costs_chart=interest_vs_transaction_costs_chart,
            loan_repayments_vs_discount_chart=loan_repayments_vs_discount_chart,

            # IMPORTANT: Pass back the selected values to maintain form state
            selected_gender=gender,
            #selected_month=month,
            selected_year=year,
            selected_loan_reason=loan_reason
        )

    except Exception as e:
        # Log the full error for debugging
        print(f"Error in business_analytics_dashboard: {e}")
        import traceback
        traceback.print_exc()

        # Return error page or default values
        return render_template(
            'business_analytics.html',
            error_message=f"An error occurred: {str(e)}",
            total_loans_issued=0,
            revenue_generated="Error",
            default_rate="Error",
            active_portfolio=0.0,
            selected_gender="All",
            selected_month="All Months",
            selected_year=datetime.now().year
        )


@app.route('/settings')
def settings():
    # Ensure business session is active
    if 'business_data' not in session:
        flash('Business session expired. Please log into business first.', 'error')
        return redirect(url_for('business_login'))

    business_id = session['business_data'].get('id')

    if not business_id:
        flash('Business ID not found in session.', 'error')
        return redirect(url_for('business_login'))


    return render_template('settings.html', business_id=business_id)


@app.route('/save-key', methods=['POST'])
def save_key():
    """Save secret key using form data"""
    print("=== SAVE-KEY FORM ENDPOINT CALLED ===")

    if session.get("user", {}).get("role") != "admin":
        flash("Access denied: Admins only.", "error")
        return render_template('unauthorized_access.html')

    # Ensure business session exists
    if 'business_data' not in session:
        flash("Business session expired. Please log into business first.", "error")
        return redirect(url_for('business_login'))

    business_id = session['business_data'].get('id')
    if not business_id:
        flash("Business ID not found in session.", "error")
        return redirect(url_for('business_login'))

    try:
        secret_key = request.form.get('secret_key')
        print(f"Received key from form: {secret_key}")

        if not secret_key or len(secret_key.strip()) == 0:
            flash('Secret key cannot be empty', 'error')
            return redirect(url_for('settings'))

        settings_tool = Settings()

        print(f"Attempting to save key: {secret_key} for business_id: {business_id}")
        response = settings_tool.save_secret_key(secret_key, business_id)

        print(f"Save response: {response}")

        if hasattr(response, 'data') and response.data:
            print("Key saved successfully")
            return redirect(url_for('key_success'))
        else:
            flash('Key saved but no confirmation received', 'warning')

        return redirect(url_for('settings'))

    except ImportError as e:
        error_msg = f"Import error - Settings class not found: {str(e)}"
        print(error_msg)
        print(traceback.format_exc())
        flash(f'Server error: {error_msg}', 'error')
        return redirect(url_for('settings'))

    except Exception as e:
        error_msg = f"Server error: {str(e)}"
        print(error_msg)
        print(traceback.format_exc())
        flash(f'Failed to save key: {error_msg}', 'error')
        return redirect(url_for('settings'))


@app.route('/key-success')
def key_success():
    # Check user role
    if session.get("user", {}).get("role") != "admin":
        flash("Access denied: Admins only.", "error")
        return render_template('unauthorized_access.html')

    # Ensure business session is active
    if 'business_data' not in session:
        flash("Business session expired. Please log into business first.", "error")
        return redirect(url_for('business_login'))

    business_id = session['business_data'].get('id')
    if not business_id:
        flash("Business ID not found in session.", "error")
        return redirect(url_for('business_login'))

    return render_template('key_success.html', business_id=business_id)


@app.route("/loan_repayment", methods=["GET", "POST"])
def loan_repayment():
    if session.get("user", {}).get("role") != "admin":
        # Block access
        flash("Access denied: Admins only.", "error")
        return render_template('unauthorized_access.html')

    # Get business_id from session
    if 'business_data' not in session:
        flash('Business session expired. Please log into business first', 'error')
        return redirect(url_for('business_login'))

    business_id = session['business_data'].get('id')

    if not business_id:
        flash('Business ID not found in session', 'error')
        return redirect(url_for('business_login'))

    if request.method == "POST":
        nrc = request.form.get("nrc").strip()
        print(f"Received NRC: {nrc}")

        repayment_tool = Repayment()
        # Pass business_id to show_loans method
        raw_loans = repayment_tool.show_loans(nrc, business_id)
        print(f"Raw loans data: {raw_loans}")

        # Pass the raw loan data without modification
        return render_template(
            "repayment.html",
            loans=raw_loans,
            searched_nrc=nrc
        )

    return render_template("repayment.html", loans=None, searched_nrc=None)


@app.route("/repayment_form/<string:loan_id>", methods=["GET"])
def repayment_form(loan_id):
    if session.get("user", {}).get("role") != "admin":
        flash("Access denied: Admins only.", "error")
        return render_template('unauthorized_access.html')

    # Get business_id from session
    if 'business_data' not in session:
        flash('Business session expired. Please log into business first', 'error')
        return redirect(url_for('business_login'))

    business_id = session['business_data'].get('id')

    if not business_id:
        flash('Business ID not found in session', 'error')
        return redirect(url_for('business_login'))

    repayment_tool = Repayment()
    loans = repayment_tool.get_loan_by_id(loan_id, business_id)

    if not loans:
        flash("Loan not found", "error")
        return redirect(url_for("loan_repayment"))

    return render_template("repayment_form.html", loan=loans)


@app.route("/process_repayment", methods=["POST"])
def process_repayment():
    if session.get("user", {}).get("role") != "admin":
        # Block access
        flash("Access denied: Admins only.", "error")
        return render_template('unauthorized_access.html')

    # Get business_id from session
    if 'business_data' not in session:
        flash('Business session expired. Please log into business first', 'error')
        return redirect(url_for('business_login'))

    business_id = session['business_data'].get('id')

    if not business_id:
        flash('Business ID not found in session', 'error')
        return redirect(url_for('business_login'))

    loan_id = request.form.get("loan_id")
    amount = request.form.get("amount")
    repayment_date = request.form.get("repayment_date")
    status = request.form.get("status")
    discount = request.form.get('discount')

    print("Loan ID:", loan_id)
    print("Amount:", amount)
    print("Repayment Date:", repayment_date)
    print("Status:", status)
    print("Business ID:", business_id)

    try:
        # Run your submit_repayment method here
        repayment_tool = Repayment()
        repayment_tool.submit_repayment(
            loan_id=loan_id,
            status=status,
            amount=amount,
            repayment_date=repayment_date,
            discount=discount,
            business_id=business_id
        )

        # Optional: Update repayment_date if stored separately
        # ... code here ...

        # If successful, render the success page
        return render_template('repayment_success.html')

    except Exception as e:
        # Handle any errors that might occur during repayment processing
        print(f"Error processing repayment: {e}")
        # You could redirect to an error page or back to the form with an error message
        flash(f"Error processing repayment: {str(e)}", "error")
        return redirect(url_for('loan_repayment'))


@app.route('/capital_management', methods=['POST', 'GET'])
def capital_management():
    # Ensure business session is active
    if 'business_data' not in session:
        flash('Business session expired. Please log into business first.', 'error')
        return redirect(url_for('business_login'))

    business_id = session['business_data'].get('id')
    if not business_id:
        flash('Business ID not found in session.', 'error')
        return redirect(url_for('business_login'))

    capital_tool = CapitalFunctions()
    owners = capital_tool.owners(business_id)  # Pass business_id to retrieve relevant owners

    if request.method == 'GET':
        return render_template('capital_management.html', owners=owners)

    elif request.method == 'POST':
        try:
            user_name = request.form.get('owner')
            amount_str = request.form.get('amount')
            status = request.form.get('status')
            transaction_file_obj = request.files.get('file')
            form_type = request.form.get('form_type')

            if not all([user_name, amount_str, status]):
                flash('Please fill in all required fields', 'error')
                return render_template('capital_management.html', owners=owners)

            try:
                amount = float(amount_str)
                if amount <= 0:
                    flash('Amount must be greater than 0', 'error')
                    return render_template('capital_management.html', owners=owners)
            except (ValueError, TypeError):
                flash('Invalid amount entered', 'error')
                return render_template('capital_management.html', owners=owners)

            if not transaction_file_obj or transaction_file_obj.filename == '':
                flash('Transaction proof file is required', 'error')
                return render_template('capital_management.html', owners=owners)

            if form_type == 'dividend':
                if session.get("user", {}).get("role") != "admin":
                    flash("Access denied: Admins only.", "error")
                    return render_template('unauthorized_access.html')

                result = capital_tool.record_given_dividend(
                    business_id=business_id,
                    amount=amount,
                    status=status,
                    user_name=user_name,
                    transaction_file_obj=transaction_file_obj
                )

                if result:
                    flash(f'Dividend payout of ${amount:,.2f} recorded successfully for {user_name}', 'success')
                else:
                    flash('Error recording dividend payout. Please try again.', 'error')

            elif form_type == 'capital':
                if session.get("user", {}).get("role") != "admin":
                    flash("Access denied: Admins only.", "error")
                    return render_template('unauthorized_access.html')

                result = capital_tool.record_capital_injection(
                    business_id=business_id,
                    user_name=user_name,
                    amount=amount,
                    status=status,
                    transaction_file_obj=transaction_file_obj
                )

                if result:
                    flash(f'Capital injection of ${amount:,.2f} recorded successfully for {user_name}', 'success')
                else:
                    flash('Error recording capital injection. Please try again.', 'error')
            else:
                flash('Invalid form submission', 'error')

            return render_template('capital_management.html', owners=owners)

        except Exception as e:
            print(f"Error in capital_management: {e}")
            flash('An unexpected error occurred. Please try again.', 'error')
            return render_template('capital_management.html', owners=owners)



@app.route('/capital_transactions', methods=['POST', 'GET'])
def capital_transactions():
    # Check if business session is active
    if 'business_data' not in session:
        flash('Business session expired. Please log into business first.', 'error')
        return redirect(url_for('business_login'))

    business_id = session['business_data'].get('id')
    if not business_id:
        flash('Business ID not found in session.', 'error')
        return redirect(url_for('business_login'))

    capital_tool = CapitalFunctions()
    transactions = capital_tool.capital_transactions(business_id)  # Use dynamic business_id here

    return render_template('capital_transactions.html', transactions=transactions)


@app.route('/manage_owners', methods=['POST', 'GET'])
def manage_owners():
    # Restrict access to admins only
    if session.get("user", {}).get("role") != "admin":
        flash("Access denied: Admins only.", "error")
        return render_template('unauthorized_access.html')

    # Ensure business session is active
    if 'business_data' not in session:
        flash('Business session expired. Please log into business first.', 'error')
        return redirect(url_for('business_login'))

    business_id = session['business_data'].get('id')
    if not business_id:
        flash('Business ID not found in session.', 'error')
        return redirect(url_for('business_login'))

    capital_tool = CapitalFunctions()
    owners = capital_tool.get_owners(business_id)  # Pass business_id to filter owners

    return render_template('manage_owners.html', owners=owners)


@app.route('/add_owner', methods=['POST', 'GET'])
def add_owner():
    if session.get("user", {}).get("role") != "admin":
        flash("Access denied: Admins only.", "error")
        return render_template('unauthorized_access.html')

    # Ensure business session is active
    if 'business_data' not in session:
        flash('Business session expired. Please log into business first.', 'error')
        return redirect(url_for('business_login'))

    business_id = session['business_data'].get('id')
    if not business_id:
        flash('Business ID not found in session.', 'error')
        return redirect(url_for('business_login'))

    # Collect form data
    user_name = request.form.get('user_name')
    email = request.form.get('email')
    phone = request.form.get('phone')
    nrc = request.form.get('nrc_number')

    # Add owner with business_id
    capital_tool = CapitalFunctions()
    response = capital_tool.add_owner(user_name, email, phone, nrc, business_id)

    # Refresh owners list for current business
    owners = capital_tool.get_owners(business_id)

    return render_template('manage_owners.html', owners=owners)



@app.route('/download_transactions', methods=['POST', 'GET'])
def download_transactions():
    # Check for valid business session
    if 'business_data' not in session:
        flash('Business session expired. Please log into business first.', 'error')
        return redirect(url_for('business_login'))

    business_id = session['business_data'].get('id')
    if not business_id:
        flash('Business ID not found in session.', 'error')
        return redirect(url_for('business_login'))

    capital_tool = CapitalFunctions()

    # Get form data
    start_date = request.form.get('start_date') or None
    end_date = request.form.get('end_date') or None
    user_name = request.form.get('user_name') or None
    amount = request.form.get('amount') or None

    # Convert amount to float if provided
    if amount:
        try:
            amount = float(amount)
        except ValueError:
            amount = None

    # Pass business_id to ensure only relevant transactions are processed
    result = capital_tool.download_capital_transactions(start_date, end_date, user_name, amount, business_id)
    print(f"DEBUG - Function result: {result}")

    if hasattr(result, 'status_code') and result.status_code == 204:
        flash('No transactions found for the selected date range.', 'warning')
        return redirect(url_for('capital_transactions'))

    return result

@app.route('/expenses', methods=['GET','POST'])
def expenses():
    # Check for valid business session
    if 'business_data' not in session:
        flash('Business session expired. Please log into business first.', 'error')
        return redirect(url_for('business_login'))

    business_id = session['business_data'].get('id')
    if not business_id:
        flash('Business ID not found in session.', 'error')
        return redirect(url_for('business_login'))

    expense_tool = Expenses()

    # Use request.args for GET parameters (since your form uses method="GET")
    start_date = request.args.get('start_date') or None
    end_date = request.args.get('end_date') or None
    expense_type = request.args.get('expense_type') or None

    # Get expense types (needed for the dropdown)
    expense_types = expense_tool.get_expense_types(business_id)

    # Check if any filters are applied
    if start_date or end_date or expense_type:
        # Use filtered data
        expense_data = expense_tool.filter_expenses(business_id, start_date, end_date, expense_type)
        # Calculate total from filtered data
        expense_total = sum(float(expense['amount']) for expense in expense_data)
    else:
        # No filters - get all expenses
        expense_data = expense_tool.get_expenses(business_id)
        # Use the existing method for total
        expense_total = expense_tool.total_expense_amount(business_id)

    return render_template(
        'expenses.html',
        expense_types=expense_types,
        expenses=expense_data,
        expense_total=expense_total
    )

@app.route('/upload_expense_type', methods=['POST', 'GET'])
def upload_expense_type():
    if session.get("user", {}).get("role") != "admin":
        flash("Access denied: Admins only.", "error")
        return render_template('unauthorized_access.html')

    # Check for valid business session
    if 'business_data' not in session:
        flash('Business session expired. Please log into business first.', 'error')
        return redirect(url_for('business_login'))

    business_id = session['business_data'].get('id')
    if not business_id:
        flash('Business ID not found in session.', 'error')
        return redirect(url_for('business_login'))

    if request.method == 'POST':
        expense_tool = Expenses()
        name = request.form.get('expenseType')

        try:
            result = expense_tool.add_expense_type(business_id, name)
            if result:
                flash('Expense type uploaded successfully.', 'success')
            else:
                flash('Error uploading expense type.', 'error')
        except Exception as e:
            print(f'Exception: {e}')
            flash('An unexpected error occurred.', 'error')

        return redirect(url_for('expenses'))

@app.route('/record_expense', methods = ['GET','POST'])
def record_expense():
    if session.get("user", {}).get("role") != "admin":
        flash("Access denied: Admins only.", "error")
        return render_template('unauthorized_access.html')

    # Check for valid business session
    if 'business_data' not in session:
        flash('Business session expired. Please log into business first.', 'error')
        return redirect(url_for('business_login'))

    business_id = session['business_data'].get('id')
    if not business_id:
        flash('Business ID not found in session.', 'error')
        return redirect(url_for('business_login'))

    if request.method == 'POST':
        expense_tool = Expenses()
        name = request.form.get('expenseType')
        amount = request.form.get('amount')

        try:
            result = expense_tool.record_expense(business_id, name, amount)
            if result:
                flash('Expense type uploaded successfully.', 'success')
            else:
                flash('Error uploading expense type.', 'error')
        except Exception as e:
            print(f'Exception: {e}')
            flash('An unexpected error occurred.', 'error')

        return redirect(url_for('expenses'))


@app.route('/download_expenses_csv', methods=['GET'])
def download_expenses_csv():
    # Check for valid business session
    if 'business_data' not in session:
        flash('Business session expired. Please log into business first.', 'error')
        return redirect(url_for('business_login'))

    business_id = session['business_data'].get('id')
    if not business_id:
        flash('Business ID not found in session.', 'error')
        return redirect(url_for('business_login'))

    # Use request.args for GET parameters
    start_date = request.args.get('startDate')
    end_date = request.args.get('endDate')

    if not start_date or not end_date:
        flash('Start and end dates are required.', 'error')
        return redirect(url_for('expenses'))

    expense_tool = Expenses()
    try:
        return expense_tool.download_csv(business_id, start_date, end_date)
    except Exception as e:
        print(f'Exception: {e}')
        flash('An error occurred while downloading the CSV.', 'error')
        return redirect(url_for('expenses'))




















@app.route('/ai_agents')
def ai_agents():
    # Check for valid business session
    if 'business_data' not in session:
        flash('Business session expired. Please log into business first.', 'error')
        return redirect(url_for('business_login'))

    business_id = session['business_data'].get('id')
    if not business_id:
        flash('Business ID not found in session.', 'error')
        return redirect(url_for('business_login'))



    return render_template('ai_agents.html')



if __name__ == '__main__':
    app.run(debug=True)
