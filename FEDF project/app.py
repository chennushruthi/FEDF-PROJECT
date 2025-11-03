from flask import Flask, render_template, request, redirect, url_for, session, jsonify, abort
from pymongo import MongoClient
from datetime import datetime, timedelta
from collections import Counter
from bson import ObjectId

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Needed for session management


# History detail route for activity/date
@app.route('/features/history/<activity>/<date>', methods=['GET'])
def history_detail(activity, date):
    user_email = session.get('user_email', 'anonymous')
    entries = []
    if activity == 'writing':
        if 'stories' in db.list_collection_names():
            entries = [doc for doc in db.stories.find({'email': user_email, 'date': date})]
    elif activity == 'diary':
        if 'diaries' in db.list_collection_names():
            entries = [doc for doc in db.diaries.find({'email': user_email, 'date': date})]
    elif activity == 'songs':
        if 'songs' in db.list_collection_names():
            entries = [doc for doc in db.songs.find({'email': user_email, 'date': date})]
    elif activity == 'gratitude':
        if 'sad_gratitude' in db.list_collection_names():
            entries = [doc for doc in db.sad_gratitude.find({'email': user_email, 'date': date})]
    else:
        abort(404)
    return render_template('history_detail.html', activity=activity, date=date, entries=entries)

# Edit history entry route
@app.route('/features/history/<activity>/<date>/<entry_id>', methods=['POST'])
def edit_history_entry(activity, date, entry_id):
    user_email = session.get('user_email', 'anonymous')
    new_content = request.form.get('content', '').strip()
    if not new_content:
        return redirect(url_for('history_detail', activity=activity, date=date))
    oid = ObjectId(entry_id)
    if activity == 'writing':
        db.stories.update_one({'_id': oid, 'email': user_email, 'date': date}, {'$set': {'story': new_content}})
    elif activity == 'diary':
        db.diaries.update_one({'_id': oid, 'email': user_email, 'date': date}, {'$set': {'diary': new_content}})
    elif activity == 'songs':
        db.songs.update_one({'_id': oid, 'email': user_email, 'date': date}, {'$set': {'song': new_content}})
    elif activity == 'gratitude':
        db.sad_gratitude.update_one({'_id': oid, 'email': user_email, 'date': date}, {'$set': {'note': new_content}})
    return redirect(url_for('history_detail', activity=activity, date=date))

# MongoDB setup (moved to top)
client = MongoClient('mongodb+srv://shruthi:123@cluster0.mysrgzf.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0')
db = client['detoxapp']
users_collection = db['users']

@app.route('/features/progress/reflection', methods=['POST'])
def save_reflection():
    user_email = session.get('user_email', 'anonymous')
    date_str = datetime.now().strftime('%Y-%m-%d')
    note = request.form.get('reflection_note', '').strip()
    if note:
        db.reflections.update_one({'email': user_email, 'date': date_str}, {'$set': {'note': note}}, upsert=True)
    return redirect(url_for('my_progress'))

# Habit logging route for Habit Tracker log buttons
@app.route('/features/habit/log/<habit>', methods=['POST'])
def log_habit(habit):
    user_email = session.get('user_email', 'anonymous')
    date_str = datetime.now().strftime('%Y-%m-%d')
    # For water, increment count; for others, set done
    if habit == 'water':
        entry = db.habits.find_one({'email': user_email, 'date': date_str, 'habit': 'water'})
        if entry:
            db.habits.update_one({'_id': entry['_id']}, {'$inc': {'count': 1}})
            new_entry = db.habits.find_one({'_id': entry['_id']})
            print(f"DEBUG: Incremented water count for {user_email} on {date_str}: {new_entry.get('count', 0)}")
            new_count = new_entry.get('count', 0)
        else:
            db.habits.insert_one({'email': user_email, 'date': date_str, 'habit': 'water', 'count': 1})
            print(f"DEBUG: Created water count for {user_email} on {date_str}: 1")
            new_count = 1
        # If AJAX, return JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'count': new_count})
        return redirect(url_for('my_progress'))
    else:
        db.habits.update_one({'email': user_email, 'date': date_str, 'habit': habit}, {'$set': {'done': True}}, upsert=True)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'done': True})
        return redirect(url_for('my_progress'))

@app.route('/features/progress/mood', methods=['POST'])
def save_mood():
    user_email = session.get('user_email', 'anonymous')
    from datetime import datetime
    date_str = datetime.now().strftime('%Y-%m-%d')
    mood_rating = int(request.form.get('mood_rating', 3))
    mood_type = request.form.get('mood_type', 'neutral')
    # Only one mood per user per day: update if exists, else insert
    existing = db.moods.find_one({'email': user_email, 'date': date_str})
    if existing:
        db.moods.update_one({'email': user_email, 'date': date_str}, {'$set': {'rating': mood_rating, 'type': mood_type}})
    else:
        db.moods.insert_one({'email': user_email, 'date': date_str, 'rating': mood_rating, 'type': mood_type})
    return redirect(url_for('my_progress'))

@app.route('/features/progress', endpoint='my_progress')
def my_progress():
    user_email = session.get('user_email', 'anonymous')
    # Example: Fetch completed challenges from MongoDB
    completed = list(db.completed_challenges.find({'email': user_email})) if 'completed_challenges' in db.list_collection_names() else []
    # Visual Analytics: Pie chart data for challenge types
    challenge_types = ['reading', 'outdoor', 'mindfulness', 'quick', 'standard', 'long', 'reflection', 'mood']
    type_counts = {ctype: 0 for ctype in challenge_types}
    for c in completed:
        ctype = c.get('type', '').lower()
        if ctype in type_counts:
            type_counts[ctype] += 1
    pie_labels = [k.capitalize() for k in type_counts.keys() if type_counts[k] > 0]
    pie_data = [type_counts[k] for k in type_counts.keys() if type_counts[k] > 0]
    pie_colors = ['#ffa000','#43a047','#1976d2','#ff7043','#ffd54f','#29b6f6','#66bb6a','#ffb300'][:len(pie_labels)]

    # Daily/Weekly Activity Data
    today = datetime.now().date()
    last_7_days = [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(6, -1, -1)]
    daily_counts = Counter([c.get('date') for c in completed if c.get('date') in last_7_days])
    daily_activity_labels = last_7_days
    daily_activity_data = [daily_counts.get(day, 0) for day in last_7_days]

    # Weekly (last 4 weeks)
    week_labels = []
    week_data = []
    for i in range(4):
        week_start = today - timedelta(days=today.weekday() + i*7)
        week_end = week_start + timedelta(days=6)
        week_label = f"{week_start.strftime('%b %d')}-{week_end.strftime('%b %d') }"
        week_labels.insert(0, week_label)
        week_dates = [(week_start + timedelta(days=d)).strftime('%Y-%m-%d') for d in range(7)]
        count = sum(1 for c in completed if c.get('date') in week_dates)
        week_data.insert(0, count)

    points = 0
    streak_days = set()
    for c in completed:
        ctype = c.get('type', '')
        effort = c.get('effort', '')
        date = c.get('date', '')
        streak_days.add(date)
        # Points allocation logic
        if ctype == 'quick':
            points += 5
        elif ctype == 'standard':
            points += 10
        elif ctype == 'long':
            points += 20
        elif ctype == 'outdoor':
            points += 15 if effort == 'medium' else 20
        elif ctype == 'mood' or ctype == 'reflection':
            points += 5
        elif ctype == 'reading':
            points += 10
        else:
            points += 5
    # Daily streak bonus
    points += 5 * len(streak_days)
    # Weekly streak bonus (example: if 7 unique days in a week)
    if len(streak_days) >= 7:
        points += 20
    # Special achievement (example: milestone)
    if len([c for c in completed if c.get('type') == 'outdoor']) >= 10:
        points += 50
    # Badges
    badges = []
    if len([c for c in completed if c.get('type') == 'outdoor']) >= 5:
        badges.append('Outdoor Explorer')
    if len(completed) >= 30:
        badges.append('Detox Master')
    # Levels
    if points <= 100:
        level = 1
        next_level_points = 101
    elif points <= 250:
        level = 2
        next_level_points = 251
    elif points <= 500:
        level = 3
        next_level_points = 501
    else:
        level = 4
        next_level_points = points + 100
    points_to_next = next_level_points - points
    # Unlockables (example)
    unlockables = []
    if points >= 100:
        unlockables.append('Motivational Quote')
    if points >= 250:
        unlockables.append('Special Wallpaper')
    if points >= 500:
        unlockables.append('Mini Challenge')
    # Mood data for chart
    mood_data = list(db.moods.find({'email': user_email})) if 'moods' in db.list_collection_names() else []
    mood_chart = []
    for m in mood_data:
        mood_chart.append({'date': m.get('date'), 'rating': m.get('rating'), 'type': m.get('type')})
    # Example insight
    outdoor_moods = [m for m in mood_data if m.get('type') == 'happy']
    insight = ''
    if outdoor_moods and len(outdoor_moods) > 2:
        insight = f"Your mood improved on days you completed outdoor challenges!"

    # Habit analytics
    habits_today = {'water': 0, 'meditation': False, 'reading': False}
    habits_streak = {'water': 0, 'meditation': 0, 'reading': 0}
    habits_goal = {'water': 8, 'meditation': 1, 'reading': 1}
    # Get today's habit logs
    today = datetime.now().strftime('%Y-%m-%d')
    for h in db.habits.find({'email': user_email, 'date': today}):
        if h['habit'] == 'water':
            habits_today['water'] = h.get('count', 0)
        elif h['habit'] == 'meditation':
            habits_today['meditation'] = h.get('done', False)
        elif h['habit'] == 'reading':
            habits_today['reading'] = h.get('done', False)
    # Calculate streaks (consecutive days)
    for habit in ['water', 'meditation', 'reading']:
        streak = 0
        for i in range(7):
            day = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            entry = db.habits.find_one({'email': user_email, 'date': day, 'habit': habit})
            if habit == 'water':
                if entry and entry.get('count', 0) >= habits_goal['water']:
                    streak += 1
                else:
                    break
            else:
                if entry and entry.get('done', False):
                    streak += 1
                else:
                    break
        habits_streak[habit] = streak

    # --- Weekly/Monthly Summary ---
    # Weekly
    week_dates_summary = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]
    week_challenges_summary = [c for c in completed if c.get('date') in week_dates_summary and c.get('completed', True)]
    week_challenges_count = len(week_challenges_summary)
    week_points_summary = 0
    for c in week_challenges_summary:
        ctype = c.get('type')
        effort = c.get('effort', '')
        if ctype == 'quick':
            week_points_summary += 5
        elif ctype == 'standard':
            week_points_summary += 10
        elif ctype == 'long':
            week_points_summary += 20
        elif ctype == 'outdoor':
            week_points_summary += 15 if effort == 'medium' else 20
        elif ctype in ['mood', 'reflection']:
            week_points_summary += 5
        elif ctype == 'reading':
            week_points_summary += 10
        else:
            week_points_summary += 5
    week_moods_summary = [m for m in mood_data if m.get('date') in week_dates_summary]
    week_mood_start_summary = week_moods_summary[0]['rating'] if week_moods_summary else 0
    week_mood_end_summary = week_moods_summary[-1]['rating'] if week_moods_summary else 0
    week_mood_change_summary = ((week_mood_end_summary - week_mood_start_summary) / week_mood_start_summary * 100) if week_mood_start_summary else 0

    week_summary = {
        'text': f"<span style='color:#1976d2;font-weight:700;'>This week you completed <span style='color:#ffa000;'>{week_challenges_count}</span>/7 challenges, earned <span style='color:#43a047;'>{week_points_summary}</span> points, and improved your mood score by <span style='color:#ff7043;'>{week_mood_change_summary:.1f}%</span>.</span>",
        'challenges': week_challenges_count,
        'points': week_points_summary,
        'mood_change': week_mood_change_summary
    }

    # Monthly summary variables (restore from previous logic)
    month_dates_summary = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(30)]
    month_challenges_summary = [c for c in completed if c.get('date') in month_dates_summary and c.get('completed', True)]
    month_challenges_count = len(month_challenges_summary)
    month_points_summary = 0
    for c in month_challenges_summary:
        ctype = c.get('type')
        effort = c.get('effort', '')
        if ctype == 'quick':
            month_points_summary += 5
        elif ctype == 'standard':
            month_points_summary += 10
        elif ctype == 'long':
            month_points_summary += 20
        elif ctype == 'outdoor':
            month_points_summary += 15 if effort == 'medium' else 20
        elif ctype in ['mood', 'reflection']:
            month_points_summary += 5
        elif ctype == 'reading':
            month_points_summary += 10
        else:
            month_points_summary += 5
    month_moods_summary = [m for m in mood_data if m.get('date') in month_dates_summary]
    month_mood_start_summary = month_moods_summary[0]['rating'] if month_moods_summary else 0
    month_mood_end_summary = month_moods_summary[-1]['rating'] if month_moods_summary else 0
    month_mood_change_summary = ((month_mood_end_summary - month_mood_start_summary) / month_mood_start_summary * 100) if month_mood_start_summary else 0
    month_summary = {
        'text': f"<span style='color:#1976d2;font-weight:700;'>This month you completed <span style='color:#ffa000;'>{month_challenges_count}</span>/30 challenges, earned <span style='color:#43a047;'>{month_points_summary}</span> points, and improved your mood score by <span style='color:#ff7043;'>{month_mood_change_summary:.1f}%</span>.</span>",
        'challenges': month_challenges_count,
        'points': month_points_summary,
        'mood_change': month_mood_change_summary
    }

    # Motivational insights
    week_motivation = "Keep going! You're building healthy habits and making real progress. Celebrate your wins and keep challenging yourself!"
    if week_mood_change_summary > 0:
        week_motivation = "Amazing! Your mood improved this week. Keep up the positive energy and try a new challenge next week!"
    elif week_mood_change_summary < 0:
        week_motivation = "It's okay to have ups and downs. Reflect on what worked and set a small goal for next week. You got this!"

    month_motivation = "Consistency is key! Every small step adds up. Keep pushing forward and reward yourself for your effort."
    if month_mood_change_summary > 0:
        month_motivation = "Fantastic! Your mood improved this month. You're on a great path—keep it up!"
    elif month_mood_change_summary < 0:
        month_motivation = "Progress isn't always linear. Take time to recharge and set new intentions for next month."

    # --- Personal Bests ---
    # Streaks
    longest_streak = max(habits_streak.values()) if habits_streak else 0
    # Challenges Completed (week/month)
    week_dates = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]
    month_dates = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(30)]
    week_challenges = [c for c in completed if c.get('date') in week_dates]
    month_challenges = [c for c in completed if c.get('date') in month_dates]
    best_week_challenges = len(week_challenges)
    best_month_challenges = len(month_challenges)
    # Habits: most days logged in week
    best_habits = {h: 0 for h in habits_today}
    for habit in habits_today:
        count = 0
        for i in range(7):
            day = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            entry = db.habits.find_one({'email': user_email, 'date': day, 'habit': habit})
            if habit == 'water':
                if entry and entry.get('count', 0) > 0:
                    count += 1
            else:
                if entry and entry.get('done', False):
                    count += 1
        best_habits[habit] = count
    # Mood: highest average mood score in a week
    week_moods = [m for m in mood_data if m.get('date') in week_dates]
    avg_mood = round(sum(m.get('rating', 0) for m in week_moods)/len(week_moods), 2) if week_moods else 0
    # Milestones: challenges completed per week and unlockables
    milestones = []
    for w in range(4):
        week_start = (datetime.now() - timedelta(days=w*7)).strftime('%Y-%m-%d')
        week_end = (datetime.now() - timedelta(days=w*7+6)).strftime('%Y-%m-%d')
        week_range = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(w*7, w*7+7)]
        week_challenges = [c for c in completed if c.get('date') in week_range]
        week_count = len(week_challenges)
        milestones.append({'label': f'Week {4-w}: {week_count} challenges completed', 'count': week_count})
        # Reading milestone: 3 reading challenges in a week
        reading_count = len([c for c in week_challenges if c.get('type') == 'reading'])
        if reading_count >= 3:
            milestones.append({'label': f'Completed {reading_count} reading challenges in a week!', 'count': reading_count, 'type': 'reading'})

    # Outdoor milestone: 10 outdoor challenges overall
    outdoor_count = len([c for c in completed if c.get('type') == 'outdoor'])
    if outdoor_count >= 10:
        milestones.append({'label': f'Completed {outdoor_count} outdoor challenges!', 'count': outdoor_count, 'type': 'outdoor'})
    # Challenge badges
    challenge_badge = None
    if best_week_challenges >= 10:
        challenge_badge = 'gold'
    elif best_week_challenges >= 7:
        challenge_badge = 'silver'
    elif best_week_challenges >= 4:
        challenge_badge = 'bronze'
    # Personal bests dict
    personal_bests = {
        'Longest Streak': longest_streak,
        'Challenges Completed (Week)': best_week_challenges,
        'Challenges Completed (Month)': best_month_challenges,
        'Habits Logged (Week)': best_habits,
        'Highest Avg Mood (Week)': avg_mood,
        'Challenge Badge': challenge_badge
    }
    # Fetch reflections for user
    reflections = []
    if 'reflections' in db.list_collection_names():
        for r in db.reflections.find({'email': user_email}).sort('date', -1):
            reflections.append({'date': r.get('date'), 'note': r.get('note')})
    return render_template(
        'my_progress.html',
        points=points,
        completed_count=len(completed),
        level=level,
        next_level_points=next_level_points,
        badges=badges,
        unlockables=unlockables,
        mood_chart=mood_chart,
        mood_insight=insight,
        habits_today=habits_today,
        habits_streak=habits_streak,
        habits_goal=habits_goal,
        personal_bests=personal_bests,
        milestones=milestones,
        pie_labels=pie_labels,
        pie_data=pie_data,
        pie_colors=pie_colors,
        daily_activity_labels=daily_activity_labels,
        daily_activity_data=daily_activity_data,
        week_labels=week_labels,
        week_data=week_data,
        reflections=reflections,
        week_summary=week_summary,
        month_summary=month_summary,
        week_motivation=week_motivation,
        month_motivation=month_motivation
    )

# History route
from flask import jsonify

@app.route('/features/history/delete', methods=['POST'])
def delete_story():
    data = request.get_json()
    user_email = session.get('user_email', 'anonymous')
    date = data.get('date')
    title = data.get('title')
    result = db.stories.delete_one({'email': user_email, 'date': date, 'title': title})
    if result.deleted_count:
        return jsonify({'success': True})
    else:
        return jsonify({'success': False})
@app.route('/features/history')
def history():
    user_email = session.get('user_email', 'anonymous')
    # Fetch writing drafts grouped by date, with titles
    writing_history = {}
    # Remove all stories with date '12/10/2025'
    db.stories.delete_many({'email': user_email, 'date': '12/10/2025'})
    # Fetch writing history grouped by date
    if 'stories' in db.list_collection_names():
        for doc in db.stories.find({'email': user_email}):
            date = doc.get('date')
            if not date:
                continue  # skip stories without a date
            title = doc.get('title', 'Untitled')
            story = doc.get('story', '')
            # Group by date
            if date not in writing_history:
                writing_history[date] = []
            writing_history[date].append({'title': title, 'story': story})
    drawing_history = [doc['drawing'] for doc in db.drawings.find({'email': user_email})] if 'drawings' in db.list_collection_names() and db.drawings.count_documents({'email': user_email}) else []
    
    # Fetch diary entries grouped by date
    diary_history = {}
    if 'diaries' in db.list_collection_names():
        for doc in db.diaries.find({'email': user_email}):
            date = doc.get('date', datetime.now().strftime('%Y-%m-%d'))
            diary_text = doc.get('diary', '')
            if date not in diary_history:
                diary_history[date] = []
            diary_history[date].append(diary_text)
    
    # Fetch songs grouped by date
    songs_history = {}
    if 'songs' in db.list_collection_names():
        for doc in db.songs.find({'email': user_email}):
            date = doc.get('date', datetime.now().strftime('%Y-%m-%d'))
            song_text = doc.get('song', '')
            if date not in songs_history:
                songs_history[date] = []
            songs_history[date].append(song_text)
    
    # Fetch gratitude notes grouped by date
    gratitude_history = {}
    if 'sad_gratitude' in db.list_collection_names():
        for doc in db.sad_gratitude.find({'email': user_email}):
            date = doc.get('date', datetime.now().strftime('%Y-%m-%d'))
            note_text = doc.get('note', '')
            if date not in gratitude_history:
                gratitude_history[date] = []
            gratitude_history[date].append(note_text)
    
    print('DEBUG writing_history:', writing_history)
    return render_template('history.html', 
                         writing_history=writing_history, 
                         drawing_history=drawing_history,
                         diary_history=diary_history,
                         songs_history=songs_history,
                         gratitude_history=gratitude_history)



app.secret_key = 'your_secret_key'  # Needed for session management
# Happy hobby route
@app.route('/features/happy/hobby')
def happy_hobby():
    return render_template('happy_hobby.html')


# Story writing route
@app.route('/features/happy/story', methods=['GET', 'POST'])
def happy_story():
    message = None
    if request.method == 'POST':
        story_text = request.form.get('story_text')
        title = request.form.get('title', 'Untitled')
        user_email = session.get('user_email', 'anonymous')
        from datetime import datetime
        date_str = datetime.now().strftime('%Y-%m-%d')
        story_doc = {'email': user_email, 'story': story_text, 'title': title, 'date': date_str}
        db.stories.insert_one(story_doc)
        print('Saved story:', story_doc)
        message = 'Your story has been saved!'
    return render_template('happy_story.html', message=message)

# Songs writing route
@app.route('/features/happy/songs', methods=['GET', 'POST'])
def happy_songs():
    message = None
    if request.method == 'POST':
        songs_text = request.form.get('songs_text')
        user_email = session.get('user_email', 'anonymous')
        date_str = datetime.now().strftime('%Y-%m-%d')
        db.songs.insert_one({'email': user_email, 'song': songs_text, 'date': date_str})
        message = 'Your song has been saved!'
    return render_template('happy_songs.html', message=message)

# Diary writing route
@app.route('/features/happy/diary', methods=['GET', 'POST'])
def happy_diary():
    message = None
    if request.method == 'POST':
        diary_text = request.form.get('diary_text')
        user_email = session.get('user_email', 'anonymous')
        date_str = datetime.now().strftime('%Y-%m-%d')
        db.diaries.insert_one({'email': user_email, 'diary': diary_text, 'date': date_str})
        message = 'Your diary entry has been saved!'
    return render_template('happy_diary.html', message=message)

# Today tasks writing route
@app.route('/features/happy/tasks', methods=['GET', 'POST'])
def happy_tasks_note():
    message = None
    if request.method == 'POST':
        tasks_text = request.form.get('tasks_text')
        user_email = session.get('user_email', 'anonymous')
        db.tasks.insert_one({'email': user_email, 'tasks': tasks_text})
        message = 'Your tasks have been saved!'
    return render_template('happy_tasks_note.html', message=message)


# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    # Development convenience: accept any non-empty email/password and log the user in.
    # If you want to enforce real authentication later, revert this logic.
    if request.method == 'POST':
        email = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if email and password:
            # Ensure a user document exists (optional) so other parts of app that expect a user work.
            if not users_collection.find_one({'email': email}):
                users_collection.insert_one({'email': email, 'password': password})
            session['logged_in'] = True
            session['user_email'] = email
            return redirect(url_for('home'))
        else:
            error = 'Please enter both email and password.'
    return render_template('login.html', error=error)


# Signup route
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    error = None
    if request.method == 'POST':
        email = request.form.get('username')
        password = request.form.get('password')
        if email and password:
            if users_collection.find_one({'email': email}):
                error = 'Account already exists.'
            else:
                users_collection.insert_one({'email': email, 'password': password})
                return redirect(url_for('login'))
        else:
            error = 'Please enter both email and password.'
    return render_template('signup.html', error=error)

# Home route
@app.route('/')
def home():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    user_email = session.get('user_email', 'anonymous')
    # Fetch completed challenges for the user
    completed = list(db.completed_challenges.find({'email': user_email})) if 'completed_challenges' in db.list_collection_names() else []
    # Get last 7 days labels and counts
    from datetime import datetime, timedelta
    today = datetime.now().date()
    last_7_days = [(today - timedelta(days=i)).strftime('%a') for i in range(6, -1, -1)]
    last_7_dates = [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(6, -1, -1)]
    daily_counts = {d: 0 for d in last_7_dates}
    for c in completed:
        date = c.get('date')
        if date in daily_counts:
            daily_counts[date] += 1
    actual_data = [daily_counts[d] for d in last_7_dates]
    # Predict next 7 days using linear regression
    import numpy as np
    from sklearn.linear_model import LinearRegression
    X = np.arange(len(actual_data)).reshape(-1, 1)
    y = np.array(actual_data)
    model = LinearRegression()
    if len(actual_data) > 1 and np.any(y):
        model.fit(X, y)
        X_pred = np.arange(len(actual_data), len(actual_data)+7).reshape(-1, 1)
        predicted_data = model.predict(X_pred).round(2).tolist()
    else:
        predicted_data = [0]*7
    predicted_labels = [(today + timedelta(days=i+1)).strftime('%a') for i in range(7)]
    return render_template('Homewithgraph.html',
        week_labels=last_7_days,
        week_data=actual_data,
        predicted_labels=predicted_labels,
        predicted_data=predicted_data)




# Features route (requires login)
@app.route('/features')
def features():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('features.html')
# Logout route
@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('user_email', None)
    return redirect(url_for('login'))


# Happy tasks route
@app.route('/features/happy')
def happy_tasks():
    return render_template('happy_tasks.html')

# Sad tasks route
@app.route('/features/sad')
def sad_tasks():
    return render_template('sad_tasks.html')

# Angry tasks route
@app.route('/features/angry')
def angry_tasks():
    return render_template('angry_tasks.html')

# Calm/Neutral tasks route
@app.route('/features/calm')
def calm_tasks():
    return render_template('calm_tasks.html')

# Drawing screen route
@app.route('/features/happy/drawing')
def happy_drawing():
    return render_template('happy_drawing.html')

# Sad gratitude note screen route
@app.route('/features/sad/gratitude', methods=['GET', 'POST'])
def sad_gratitude():
    message = None
    if request.method == 'POST':
        note_text = request.form.get('note_text')
        user_email = session.get('user_email', 'anonymous')
        date_str = datetime.now().strftime('%Y-%m-%d')
        db.sad_gratitude.insert_one({'email': user_email, 'note': note_text, 'date': date_str})
        message = 'Your gratitude note has been saved!'
    return render_template('sad_gratitude.html', message=message)

# Sad walk timer screen route
@app.route('/features/sad/walk')
def sad_walk():
    return render_template('sad_walk.html')

# Angry tasks by level route
@app.route('/features/angry/level/<int:level>')
def angry_tasks_level(level):
    # Define tasks for each angry level
    angry_tasks_by_level = {
        1: [
            {'icon': '🧘', 'text': 'Take 5 deep breaths'},
            {'icon': '💧', 'text': 'Drink a glass of water'},
            {'icon': '🚶', 'text': 'Step away for 2 minutes'}
        ],
        2: [
            {'icon': '✍️', 'text': 'Write down your thoughts'},
            {'icon': '🧎', 'text': 'Stretch for 5 minutes'},
            {'icon': '🎶', 'text': 'Listen to calming music'}
        ],
        3: [
            {'icon': '🏋️', 'text': 'Do a quick workout (push-ups, squats)'},
            {'icon': '🛌', 'text': 'Take a short nap / sleep'},
            {'icon': '📓', 'text': 'Journal “what’s making me upset?”'}
        ],
        4: [
            {'icon': '🚶', 'text': 'Go for a walk outside'},
            {'icon': '🎧', 'text': 'Do a 5–10 min guided meditation'},
            {'icon': '🚿', 'text': 'Wash your face / take a cold shower'}
        ],
        5: [
            {'icon': '📴', 'text': 'Turn off phone & rest'},
            {'icon': '🛌', 'text': 'Sleep to reset'},
            {'icon': '☎️', 'text': 'Call a trusted friend to vent safely'},
            {'icon': '🫁', 'text': 'Practice 4-7-8 breathing'}
        ]
    }
    tasks = angry_tasks_by_level.get(level, [])
    return render_template('angry_tasks_level.html', level=level, tasks=tasks)

# Angry note writing route for Mild level
@app.route('/features/angry/note', methods=['GET', 'POST'])
def angry_note():
    message = None
    note_text = None
    if request.method == 'POST':
        note_text = request.form.get('note_text')
        user_email = session.get('user_email', 'anonymous')
        db.angry_notes.insert_one({'email': user_email, 'note': note_text})
        message = 'Your note has been saved!'
    return render_template('angry_note.html', message=message, note_text=note_text)

# Angry music screen for Mild level
@app.route('/features/angry/music')
def angry_music():
    return render_template('angry_music.html')

# Angry journal writing route for Moderate level
@app.route('/features/angry/journal', methods=['GET', 'POST'])
def angry_journal():
    message = None
    journal_text = None
    if request.method == 'POST':
        journal_text = request.form.get('journal_text')
        user_email = session.get('user_email', 'anonymous')
        db.angry_journals.insert_one({'email': user_email, 'journal': journal_text})
        message = 'Your journal entry has been saved!'
    return render_template('angry_journal.html', message=message, journal_text=journal_text)

# Angry meditation timer screen for Strong level
@app.route('/features/angry/meditation')
def angry_meditation():
    return render_template('angry_meditation.html')

# Calm books screen for Calm/Neutral tasks
@app.route('/features/calm/books')
def calm_books():
    return render_template('calm_books.html')

# Book story screen for Calm/Neutral tasks
@app.route('/features/calm/book/<book_id>')
def book_story(book_id):
    stories = {
        'pride': {
            'title': 'Pride and Prejudice by Jane Austen',
            'text': "Pride and Prejudice is a romantic novel that follows Elizabeth Bennet as she navigates issues of manners, upbringing, morality, education, and marriage in the landed gentry of early 19th-century England. The story centers on Elizabeth's evolving relationship with the proud Mr. Darcy, exploring themes of love, reputation, and class."},
        'fault': {
            'title': 'The Fault in Our Stars by John Green',
            'text': "The Fault in Our Stars tells the story of Hazel Grace Lancaster, a teenager living with cancer, and Augustus Waters, a charming boy she meets at a support group. Their journey is one of love, heartbreak, and hope as they travel to Amsterdam to meet Hazel's favorite author and confront the realities of life and death together."},
        'mebefore': {
            'title': 'Me Before You by Jojo Moyes',
            'text': "Me Before You is a moving love story about Louisa Clark, a quirky young woman, and Will Traynor, a wealthy man left paralyzed after an accident. As Louisa becomes Will's caregiver, their relationship deepens, challenging both to find meaning and joy in life despite difficult circumstances."}
    }
    # If book_id is not in stories, show a generic message
    generic_titles = {
        'it': 'It by Stephen King',
        'hillhouse': 'The Haunting of Hill House by Shirley Jackson',
        'dracula': 'Dracula by Bram Stoker',
        'gonegirl': 'Gone Girl by Gillian Flynn',
        'dragontattoo': 'The Girl with the Dragon Tattoo by Stieg Larsson',
        'silence': 'The Silence of the Lambs by Thomas Harris',
        'mockingbird': 'To Kill a Mockingbird by Harper Lee',
        '1984': '1984 by George Orwell',
        'gatsby': 'The Great Gatsby by F. Scott Fitzgerald'
    }
    story = stories.get(book_id)
    if not story:
        title = generic_titles.get(book_id, 'Unknown Book')
        text = "Story details for this book are not available, but you can search online for a summary or review!"
        return render_template('book_story.html', book_title=title, story_text=text)
    return render_template('book_story.html', book_title=story['title'], story_text=story['text'])

# Calm challenges screen route
@app.route('/features/calm/challenges')
def calm_challenges():
    challenges = [
        "Read 20 pages in one sitting",
        "Finish a novel in a week",
        "Write a review for a book you've read",
        "Recommend a book to a friend",
        "Read a book from a new genre",
        "Read a classic novel",
        "Read a book by an author you've never read before",
        "Join a book club discussion",
        "Read a book and watch its movie adaptation",
        "Read a book published this year"
    ]
    return render_template('calm_challenges.html', challenges=challenges)

# 7-Day Detox plan screen route
@app.route('/features/calm/challenges/7day')
def seven_day_detox():
    plan = [
        {
            'day': 'Day 1 – Awareness',
            'details': [
                'Track your screen time for the whole day (just observe, no changes).',
                'Write down your top 3 most used apps.'
            ]
        },
        {
            'day': 'Day 2 – Cut Notifications',
            'details': [
                'Turn off non-essential notifications.',
                'Phone check limit: only 3 times in the morning, 3 in the evening.'
            ]
        },
        {
            'day': 'Day 3 – No-Phone Zone',
            'details': [
                'Create 1 no-phone space (like your dining table or bedroom).',
                'Replace that time with journaling or stretching.'
            ]
        },
        {
            'day': 'Day 4 – Morning Detox',
            'details': [
                'No phone for the first 30 minutes after waking up.',
                'Instead: read, stretch, or drink water.'
            ]
        },
        {
            'day': 'Day 5 – Outdoor Break',
            'details': [
                'Spend 30 minutes outdoors without your phone.',
                'Observe surroundings or talk to someone in person.'
            ]
        },
        {
            'day': 'Day 6 – Digital Swap',
            'details': [
                'Replace 1 hour of scrolling with 1 hour of reading or a hobby.',
                'Log what you did and how it felt.'
            ]
        },
        {
            'day': 'Day 7 – Reflection Day',
            'details': [
                'No social media for 24 hours.',
                'Journal: How did the detox week make you feel? What will you continue?'
            ]
        }
    ]
    return render_template('seven_day_detox.html', plan=plan)

# Reading challenge plan screen route
@app.route('/features/calm/challenges/reading')
def reading_challenge():
    plan = [
        "Read at least 5 pages daily.",
        "Try a new genre you don’t usually read.",
        "Find and note one inspiring quote.",
        "Read for 15 minutes without distractions.",
        "Summarize what you read in 3 sentences."
    ]
    return render_template('reading_challenge.html', plan=plan)

# Outdoor challenge options screen route
@app.route('/features/calm/challenges/outdoor')
def outdoor_challenge():
    categories = [
        {
            'name': 'Physical / Fitness Challenges',
            'icon': 'fa-dumbbell',
            'desc': 'Get active outdoors with fitness goals.'
        },
        {
            'name': 'Mindfulness / Nature Challenges',
            'icon': 'fa-leaf',
            'desc': 'Practice mindfulness and connect with nature.'
        },
        {
            'name': 'Social / Fun Challenges',
            'icon': 'fa-users',
            'desc': 'Enjoy outdoor activities with friends or family.'
        },
        {
            'name': 'Adventure / Exploration Challenges',
            'icon': 'fa-hiking',
            'desc': 'Explore new places and try new adventures.'
        }
    ]
    return render_template('outdoor_challenge.html', categories=categories)

# Physical / Fitness Challenges details screen
@app.route('/features/calm/challenges/outdoor/physical')
def outdoor_physical_challenge():
    challenges = [
        "Take a 30-minute walk in nature or your neighborhood.",
        "Do a short outdoor workout or yoga session.",
        "Try a new sport or activity (skipping, cycling, frisbee).",
        "Run or jog for 15–20 minutes.",
        "Do a mini scavenger hunt outside (find 5 different types of leaves, rocks, etc.)."
    ]
    return render_template('outdoor_physical_challenge.html', challenges=challenges)

# Mindfulness / Nature Challenges details screen
@app.route('/features/calm/challenges/outdoor/mindfulness')
def outdoor_mindfulness_challenge():
    challenges = [
        "Sit outside for 10 minutes and observe your surroundings.",
        "Take photos of interesting things in nature.",
        "Practice deep breathing while walking outdoors.",
        "Listen to the sounds around you for 5 minutes and note them mentally."
    ]
    return render_template('outdoor_mindfulness_challenge.html', challenges=challenges)

# Social / Fun Challenges details screen
@app.route('/features/calm/challenges/outdoor/social')
def outdoor_social_challenge():
    challenges = [
        "Invite a friend or family member for an outdoor activity.",
        "Do a random act of kindness outside (help someone, give a compliment).",
        "Draw or write something inspired by nature."
    ]
    return render_template('outdoor_social_challenge.html', challenges=challenges)

# Social / Fun Challenge note area screen
@app.route('/features/calm/challenges/outdoor/social/note')
def outdoor_social_note():
    return render_template('outdoor_social_note.html')

# Adventure / Exploration Challenges details screen
@app.route('/features/calm/challenges/outdoor/adventure')
def outdoor_adventure_challenge():
    challenges = [
        "Explore a nearby park, trail, or new street you’ve never visited.",
        "Try geocaching or treasure hunting outside.",
        "Spend time star-gazing or cloud-watching."
    ]
    return render_template('outdoor_adventure_challenge.html', challenges=challenges)

# Happy gratitude note screen route
@app.route('/features/happy/gratitude', methods=['GET', 'POST'])
def happy_gratitude():
    message = None
    if request.method == 'POST':
        note_text = request.form.get('note_text')
        user_email = session.get('user_email', 'anonymous')
        db.happy_gratitude.insert_one({'email': user_email, 'note': note_text})
        message = 'Your gratitude note has been saved!'
    return render_template('happy_gratitude.html', message=message)

if __name__ == '__main__':
    app.run(debug=True)