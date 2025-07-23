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



load_dotenv()  # This loads variables from .env into the environment
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


@app.route('/business_login', methods=['GET', 'POST'])  # Added missing slash
def business_login():
    if request.method == 'GET':
        return render_template("user_login_signup.html")  # Show the form

    # Handle POST request
    business_email = request.form.get('business_email')
    business_password = request.form.get('business_password')

    auth = UserAuthentication()

    try:
        result = auth.business_login(business_email, business_password)

        if result.get("success", False):  # Assuming your method returns a dict with success key
            # Store business info in session
            session['business_data'] = result.get('business_data', {})
            flash('Business login successful!', 'success')

            # Redirect to the same page but now show user login form
            # You'll need to pass business data to show the user login form
            return render_template("user_login_signup.html",
                                   show_user_login=True,
                                   business_name=result.get('business_data', {}).get('name'))
        else:
            flash('Wrong business credentials', 'error')
            return render_template("user_login_signup.html")

    except Exception as e:
        print(f'Exception: {e}')
        flash('An error occurred during business login', 'error')
        return render_template("user_login_signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        # Check if business is logged in
        if 'business_data' not in session:
            flash('Please log into business first', 'error')
            return redirect(url_for('business_login'))
        return render_template("user_login_signup.html",
                               show_user_login=True,
                               business_name=session['business_data'].get('name'))

    # Handle POST request (form submission)
    # Check if business is still in session
    if 'business_data' not in session:
        flash('Business session expired. Please log into business first', 'error')
        return redirect(url_for('business_login'))

    auth = UserAuthentication()
    email = request.form["email"]
    password = request.form["password"]
    response = auth.login(email, password)

    # Check if login was successful
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

@app.route('/unauthorized_access')
def unauthorized_access():

    return render_template('unauthorized_access.html')


@app.route('/overview_dashboard', methods=['GET', 'POST'])
def overview_dashboard():
    loan_tool = Loans()
    loan_tool.update_overdue_loans()

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
                'total_disbursed': f"ZMK {overview_tool.total_disbursed(selected_period):,.2f}",
                'total_repaid': f"ZMK {overview_tool.total_repaid(selected_period):,.2f}",
                'outstanding_balance': f"ZMK {overview_tool.outstanding_balance(selected_period):,.2f}",
                'expected_interest': f"ZMK {overview_tool.expected_interest(selected_period):,.2f}",
                'average_loan_size': f"ZMK {overview_tool.average_loan_size(selected_period):,.2f}",
                'average_duration': f"{overview_tool.average_duration(selected_period):,.0f} days",
                'active_loans': f"{overview_tool.active_loans(selected_period):,}",
                'default_rate': f"{overview_tool.default_rate(selected_period)}%",
                'transaction_costs' : f"ZMK{overview_tool.total_transaction_costs(selected_period)}",
                'discount_costs' : f"ZMK{overview_tool.total_discounts_given(selected_period)}",

                'available_cash': overview_tool.available_cash(),
                'gender_chart': chart_tool.borrowers_by_gender(selected_period),
                'status_distribution_chart': chart_tool.loan_status_distribution(selected_period)
            }
            return jsonify(response_data)
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    # Existing GET route logic
    selected_period = request.args.get('period', 'Last 30 Days')
    overview_tool = OverviewMetrics()
    chart_tool = Charts()

    available_cash = overview_tool.available_cash()
    total_disbursed = f"ZMK {overview_tool.total_disbursed(selected_period):,.2f}"
    total_repaid = f"ZMK {overview_tool.total_repaid(selected_period):,.2f}"
    outstanding_balance = f"ZMK {overview_tool.outstanding_balance(selected_period):,.2f}"
    expected_interest = f"ZMK {overview_tool.expected_interest(selected_period):,.2f}"
    average_loan_size = f"ZMK {overview_tool.average_loan_size(selected_period):,.2f}"
    average_duration = f"{overview_tool.average_duration(selected_period):,.0f} days"
    active_loans = f"{overview_tool.active_loans(selected_period):,}"
    default_rate = f"{overview_tool.default_rate(selected_period)}%"
    transaction_costs = f"ZMK{overview_tool.total_transaction_costs(selected_period)}"
    discount_costs = f"ZMK{overview_tool.total_discounts_given(selected_period)}"

    recent_borrowers = overview_tool.recent_borrowers()
    location_summary = overview_tool.borrowers_by_location(selected_period)
    weekly_loans_due = overview_tool.weekly_loans_due()
    gender_chart = chart_tool.borrowers_by_gender(selected_period)
    status_distribution_chart = chart_tool.loan_status_distribution(selected_period)

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
                         transaction_costs = transaction_costs,
                         gender_chart=gender_chart,
                         status_distribution_chart=status_distribution_chart,
                         recent_borrowers=recent_borrowers,
                         location_summary=location_summary,
                         weekly_loans_due=weekly_loans_due)


@app.route('/loans_data', methods=['POST', 'GET'])
def loans_data():
    loans_tool = Loans()
    overview_tool = OverviewMetrics()

    from_date = request.args.get('start_date')
    to_date = request.args.get('end_date')
    loan_type = request.args.get('loan_type')

    # Since form method is GET, get search query from request.args
    search_query = request.args.get('query')

    if from_date or to_date or loan_type:
        loans = loans_tool.filtered_loans(from_date, to_date, loan_type)
    elif search_query:
        loans = loans_tool.search_by_id(search_query)
    else:
        loans = overview_tool.recent_borrowers()

    return render_template('loans_data.html', loans=loans)

@app.route('/download_loans_csv', methods=['POST', 'GET'])
def download_loans_csv():
    loans_tool = Loans()
    start_date = request.form.get('download_start_date')
    end_date = request.form.get('download_end_date')

    try:
        return loans_tool.download_csv(start_date, end_date)
    except Exception as e:
        print(f'Exception: {e}')
        flash(f'Error: {e}')
        return redirect(request.referrer)



@app.route('/search_borrower', methods=['GET', 'POST'])
def search_borrower():
    # Check if this is a search request (has nrc_search parameter)
    nrc_number = request.args.get('nrc_search')

    if nrc_number:
        # User has submitted a search, get the borrower data
        registration_tool = Registration()
        borrower_data = registration_tool.get_borrower_id(nrc=nrc_number)

        # Return the results template
        return render_template('borrower_results.html', borrower_data=borrower_data)
    else:
        # No search parameter, show the search form
        return render_template('search_borrower.html')



@app.route('/borrower_information')
def borrower_information():
    borrower_id = request.args.get('borrower_id')

    # get the loan_id using the borrower id
    registration_tool = Registration()
    loan_id = registration_tool.get_loan_id(borrower_id)

    borrower_data = registration_tool.get_borrower_data(borrower_id)

    borrower_information_tool = BorrowerInformation()

    payment_history = borrower_information_tool.get_borrower_payment_history(loan_id)

    outstanding_debts = borrower_information_tool.total_outstanding_debts(borrower_id)

    default_assessment = borrower_information_tool.default_risk_assessment(borrower_id)

    credit_status = borrower_information_tool.account_status(borrower_id)

    recent_borrower_history = borrower_information_tool.recent_borrower_history(borrower_id)

    return render_template(
        'borrower_information.html',
        borrower_data=borrower_data,
        payment_history=payment_history,
        outstanding_debts=outstanding_debts,
        default_assessment=default_assessment,
        credit_status=credit_status,
        recent_borrower_history=recent_borrower_history
    )

@app.route('/borrower_data', methods = ['POST','GET'])
def borrower_data():
    borrower_tool = BorrowerInformation()
    borrowers = borrower_tool.get_borrowers()

    return render_template('borrowers_data.html', borrowers = borrowers)

@app.route('/loan_form')
def loan_form():
    """Display the loan form"""
    if session.get("user", {}).get("role") != "admin":
        # Block access
        flash("Access denied: Admins only.", "error")
        return render_template('unauthorized_access.html')

    borrower_id = request.args.get('borrower_id')

    if not borrower_id:
        flash('Borrower ID is required', 'error')
        return redirect(url_for('search_borrower'))

    loan_tool = Loans()
    borrower_identity = loan_tool.borrower_identity(borrower_id)

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
        result = registration_tool.register_new_borrower(
            name=name,
            gender=gender,
            location=location,
            nrc_number=nrc_number,
            mobile=mobile,
            occupation=occupation,
            birth_date=birth_date,
            notes=notes
        )

        if result:
            flash('Borrower registered successfully!', 'success')
            return render_template(
                'successful_borrower_submitted.html',
                borrower_name = name,
                nrc_number = nrc_number,
                mobile = mobile,
                location = location
            )
        else:
            flash('Error registering borrower. Please try again.', 'error')

        return redirect(url_for('register_borrower'))


@app.route('/submit-loan', methods=['POST'])
def submit_loan():
    """Handle loan form submission"""
    if session.get("user", {}).get("role") != "admin":
        # Block access
        flash("Access denied: Admins only.", "error")
        return render_template('unauthorized_access.html')

    try:
        # Get form data - FIX: Get borrower_id from form, not args
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

        # Enhanced debug prints
        print(f"=== LOAN SUBMISSION DEBUG ===")
        print(f"borrower_id: {borrower_id}")
        print(f"amount: {amount} (type: {type(amount)})")
        print(f"interest_rate: {interest_rate}")
        print(f"duration_days: {duration_days}")
        print(f"due_date: {due_date}")
        print(f"contract_file: {contract_file}")
        print(f"contract_file.filename: {contract_file.filename if contract_file else 'None'}")

        # Validate required fields
        if not all([borrower_id, amount, interest_rate, duration_days, due_date]):
            print("ERROR: Missing required fields")
            flash('Please fill in all required fields', 'error')
            return redirect(url_for('loan_form', borrower_id=borrower_id))

        if not contract_file or contract_file.filename == '':
            print("ERROR: Missing contract file")
            flash('Contract file is required', 'error')
            return redirect(url_for('loan_form', borrower_id=borrower_id))

        print("All validations passed, submitting loan...")

        # Submit loan
        loan_tool = Loans()
        loan_id = loan_tool.old_borrower_loan(
            borrower_id=borrower_id,
            amount=amount,
            transaction_costs=transaction_costs,
            interest_rate=interest_rate,
            duration_days=duration_days,
            due_date=due_date,
            loan_reason=loan_reason,
            contract_file_obj=contract_file,
            collateral_files_list=collateral_images if collateral_images else None
        )

        print(f"Loan submission result - loan_id: {loan_id}")

        if loan_id:
            print("SUCCESS: Loan submitted successfully, rendering success page...")
            flash('Loan application submitted successfully!', 'success')

            # Debug the template variables
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
            print("ERROR: Loan submission failed")
            flash('Error submitting loan application. Please try again.', 'error')
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
    try:
        # Get form data with proper error handling
        gender = request.form.get('gender')
        month = request.form.get('months')
        year_str = request.form.get('year')

        # Debug: Print what we're getting from the form
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

        print(f"Final values - Gender: {gender}, Month: {month}, Year: {year}")

        # Initialize analytics tool
        customer_analytics_tool = CustomerAnalytics()

        # kpi cards data variables
        total_customers = customer_analytics_tool.total_customers(gender, month, year)
        best_location = customer_analytics_tool.best_location(gender, year, month)  # Note: fixed parameter order
        worst_location = customer_analytics_tool.worst_location(gender, year, month)  # Note: fixed parameter order
        average_amount = customer_analytics_tool.average_loan_amount(gender, year, month)  # Note: fixed parameter order

        # chart variables
        loans_location_chart = customer_analytics_tool.loans_by_location_chart(gender, year, month)
        loans_occupation_chart = customer_analytics_tool.loans_by_occupation_chart(gender, year, month)
        age_group_chart = customer_analytics_tool.age_group_radial_bar_chart(gender, year, month)

        # Chart variables
        loans_location_chart = customer_analytics_tool.loans_by_location_chart(gender, year, month)
        loans_occupation_chart = customer_analytics_tool.loans_by_occupation_chart(gender, year, month)
        age_group_chart = customer_analytics_tool.age_group_radial_bar_chart(gender, year, month)

        # location performance kpi cards
        location_scores = customer_analytics_tool.location_performance_ranking(gender, year, month)

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

            location_scores = location_scores
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
        # Get form data with proper error handling
        gender = request.form.get('gender')
        month = request.form.get('months')
        year_str = request.form.get('year')
        loan_reason = request.form.get('loan_reason')

        # Debug: Print what we're getting from the form
        print(f"Debug - Gender: {gender}, Month: {month}, Year: {year_str}, Loan Reason: {loan_reason}")
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

        print(f"Final values - Gender: {gender}, Month: {month}, Year: {year}, Loan Reason: {loan_reason}")

        business_analytics_tool = BusinessAnalytics()

        total_loans_issued = business_analytics_tool.total_loans_issued(gender, month, year)
        revenue_generated = business_analytics_tool.total_revenue_generated(gender, month, year)
        default_rate = business_analytics_tool.default_rate(gender, month, year)
        active_portfolio = business_analytics_tool.active_portfolio(gender, month, year)

        # Only generate chart if loan_reason is provided
        loan_reason_trend_chart = None
        if loan_reason:
            loan_reason_trend_chart = business_analytics_tool.loan_reason_trend_chart(gender, year, loan_reason)

        interest_vs_transaction_costs_chart = business_analytics_tool.interest_vs_transaction_costs_chart(gender, year)
        loan_repayments_vs_discount_chart = business_analytics_tool.loan_repayments_vs_discount_chart(gender, year)

        return render_template(
            'business_analytics.html',
            total_loans_issued=total_loans_issued,
            revenue_generated=revenue_generated,
            default_rate=default_rate,
            active_portfolio=active_portfolio,
            loan_reason_trend_chart=loan_reason_trend_chart,
            interest_vs_transaction_costs_chart = interest_vs_transaction_costs_chart,
            loan_repayments_vs_discount_chart = loan_repayments_vs_discount_chart,

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

    return render_template('settings.html')


@app.route('/save-key', methods=['POST'])
def save_key():
    """Save secret key using form data"""
    print("=== SAVE-KEY FORM ENDPOINT CALLED ===")

    if session.get("user", {}).get("role") != "admin":
        # Block access
        flash("Access denied: Admins only.", "error")
        return render_template('unauthorized_access.html')

    try:
        # Get the key from form data
        secret_key = request.form.get('secret_key')
        print(f"Received key from form: {secret_key}")

        if not secret_key:
            print("No secret key provided in form")
            flash('No secret key provided', 'error')
            return redirect(url_for('settings'))

        if len(secret_key.strip()) == 0:
            print("Empty secret key provided")
            flash('Secret key cannot be empty', 'error')
            return redirect(url_for('settings'))

        print("Creating Settings instance...")
        settings_tool = Settings()

        print(f"Attempting to save key: {secret_key}")
        response = settings_tool.save_secret_key(secret_key)

        print(f"Save response: {response}")

        # Check if save was successful
        if hasattr(response, 'data') and response.data:
            print("Key saved successfully")
            return redirect(url_for('key_success'))
        else:
            print("No data returned from save operation")
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
    if session.get("user", {}).get("role") != "admin":
        # Block access
        flash("Access denied: Admins only.", "error")
        return render_template('unauthorized_access.html')

    return render_template('key_success.html')



@app.route('/capital_management', methods=['POST', 'GET'])
def capital_management():
    capital_tool = CapitalFunctions()
    owners = capital_tool.owners()

    if request.method == 'GET':
        # Just render the template with owners list
        return render_template('capital_management.html', owners=owners)

    elif request.method == 'POST':
        try:
            # Get form data
            user_name = request.form.get('owner')
            amount_str = request.form.get('amount')
            status = request.form.get('status')
            transaction_file_obj = request.files.get('file')  # Use request.files for file uploads

            # Validate required fields
            if not all([user_name, amount_str, status]):
                flash('Please fill in all required fields', 'error')
                return render_template('capital_management.html', owners=owners)

            # Convert amount to float
            try:
                amount = float(amount_str)
                if amount <= 0:
                    flash('Amount must be greater than 0', 'error')
                    return render_template('capital_management.html', owners=owners)
            except (ValueError, TypeError):
                flash('Invalid amount entered', 'error')
                return render_template('capital_management.html', owners=owners)

            # Validate file upload
            if not transaction_file_obj or transaction_file_obj.filename == '':
                flash('Transaction proof file is required', 'error')
                return render_template('capital_management.html', owners=owners)

            # Determine which form was submitted based on which button was clicked
            # You'll need to add a hidden field to distinguish between the two forms
            form_type = request.form.get('form_type')

            if form_type == 'dividend':
                if session.get("user", {}).get("role") != "admin":
                    # Block access
                    flash("Access denied: Admins only.", "error")
                    return render_template('unauthorized_access.html')

                    # Record dividend payout
                result = capital_tool.record_given_dividend(
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
                # Record capital injection
                if session.get("user", {}).get("role") != "admin":
                    # Block access
                    flash("Access denied: Admins only.", "error")
                    return render_template('unauthorized_access.html')

                result = capital_tool.record_capital_injection(
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


@app.route("/loan_repayment", methods=["GET", "POST"])
def loan_repayment():
    if session.get("user", {}).get("role") != "admin":
        # Block access
        flash("Access denied: Admins only.", "error")
        return render_template('unauthorized_access.html')

    if request.method == "POST":
        nrc = request.form.get("nrc").strip()
        print(f"Received NRC: {nrc}")

        repayment_tool = Repayment()
        raw_loans = repayment_tool.show_loans(nrc)
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

    repayment_tool = Repayment()
    loans = repayment_tool.get_loan_by_id(loan_id)

    if not loans:
        flash("Loan not found", "error")
        return redirect(url_for("loan_repayment"))

    return render_template("repayment_form.html", loan=loans[0])


@app.route("/process_repayment", methods=["POST"])
def process_repayment():

    if session.get("user", {}).get("role") != "admin":
        # Block access
        flash("Access denied: Admins only.", "error")
        return render_template('unauthorized_access.html')

    loan_id = request.form.get("loan_id")
    amount = request.form.get("amount")
    repayment_date = request.form.get("repayment_date")
    status = request.form.get("status")
    discount = request.form.get('discount')

    print("Loan ID:", loan_id)
    print("Amount:", amount)
    print("Repayment Date:", repayment_date)
    print("Status:", status)

    try:
        # Run your submit_repayment method here
        repayment_tool = Repayment()
        repayment_tool.submit_repayment(
            loan_id = loan_id,
            status = status,
            amount = amount,
            repayment_date = repayment_date,
            discount = discount
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


@app.route('/capital_transactions', methods = ['POST', 'GET'])
def capital_transactions():
    capital_tool = CapitalFunctions()

    transactions = capital_tool.capital_transactions(3)
    return render_template('capital_transactions.html',
                           transactions = transactions)

@app.route('/manage_owners', methods = ['POST','GET'])
def manage_owners():
    if session.get("user", {}).get("role") != "admin":
        # Block access
        flash("Access denied: Admins only.", "error")
        return render_template('unauthorized_access.html')

    capital_tool = CapitalFunctions()

    owners = capital_tool.get_owners()

    return render_template('manage_owners.html', owners = owners)

@app.route('/add_owner', methods = ['POST','GET'])
def add_owner():
    if session.get("user", {}).get("role") != "admin":
        # Block access
        flash("Access denied: Admins only.", "error")
        return render_template('unauthorized_access.html')

    user_name = request.form.get('user_name')
    email = request.form.get('email')
    phone = request.form.get('phone')
    nrc = request.form.get('nrc_number')

    # add owner
    capital_tool = CapitalFunctions()
    response = capital_tool.add_owner(user_name, email, phone, nrc)

    owners = capital_tool.get_owners()

    return render_template('manage_owners.html', owners=owners)


@app.route('/download_transactions', methods=['POST', 'GET'])
def download_transactions():
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

    # Use your existing function
    result = capital_tool.download_capital_transactions(start_date, end_date, user_name, amount)
    print(f"DEBUG - Function result: {result}")

    # Check if the result is a 204 No Content response (no transactions found)
    if hasattr(result, 'status_code') and result.status_code == 204:
        flash('No transactions found for the selected date range.', 'warning')
        return redirect(url_for('capital_transactions'))  # Replace with your actual route name

    # If it's a successful response (CSV download), return it
    return result





@app.route('/ai_agents')
def ai_agents():
    return render_template('ai_agents.html')




if __name__ == '__main__':
    app.run()