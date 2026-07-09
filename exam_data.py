"""
Sample exam/question bank, keyed by a unique exam code students enter to join.
In a real deployment this would live in a database; kept as a plain dict here
so the whole project stays dependency-light and easy to demo/extend.

Each question:
    id       -- unique string id (stable across renders)
    text     -- question text
    options  -- list of answer choices
    answer   -- index (0-based) of the correct option in `options`
"""

EXAMS = {
    "MATH101": {
        "title": "Basic Mathematics Assessment",
        "duration_minutes": 15,
        "questions": [
            {
                "id": "q1",
                "text": "What is the value of 12 x 8?",
                "options": ["96", "88", "104", "72"],
                "answer": 0,
            },
            {
                "id": "q2",
                "text": "Solve for x: 2x + 5 = 17",
                "options": ["5", "6", "7", "8"],
                "answer": 1,
            },
            {
                "id": "q3",
                "text": "What is the square root of 144?",
                "options": ["10", "11", "12", "14"],
                "answer": 2,
            },
            {
                "id": "q4",
                "text": "What is 15% of 200?",
                "options": ["20", "25", "30", "35"],
                "answer": 2,
            },
            {
                "id": "q5",
                "text": "If a triangle has angles 60 degrees and 70 degrees, what is the third angle?",
                "options": ["40 degrees", "50 degrees", "60 degrees", "70 degrees"],
                "answer": 1,
            },
        ],
    },
    "CS101": {
        "title": "Introduction to Computer Science",
        "duration_minutes": 15,
        "questions": [
            {
                "id": "q1",
                "text": "Which data structure uses LIFO (Last In First Out) order?",
                "options": ["Queue", "Stack", "Linked List", "Array"],
                "answer": 1,
            },
            {
                "id": "q2",
                "text": "What is the time complexity of binary search on a sorted array?",
                "options": ["O(n)", "O(n^2)", "O(log n)", "O(1)"],
                "answer": 2,
            },
            {
                "id": "q3",
                "text": "Which of these is NOT a programming paradigm?",
                "options": ["Object-Oriented", "Functional", "Procedural", "Alphabetical"],
                "answer": 3,
            },
            {
                "id": "q4",
                "text": "In C++, which keyword is used to define a constant?",
                "options": ["final", "const", "static", "readonly"],
                "answer": 1,
            },
            {
                "id": "q5",
                "text": "What does 'HTTP' stand for?",
                "options": [
                    "HyperText Transfer Protocol",
                    "High Transfer Text Protocol",
                    "HyperText Transmission Process",
                    "Host Transfer Text Protocol",
                ],
                "answer": 0,
            },
            {
                "id": "q6",
                "text": "Which sorting algorithm has the best average-case time complexity?",
                "options": ["Bubble Sort", "Selection Sort", "Merge Sort", "Insertion Sort"],
                "answer": 2,
            },
        ],
    },
}


def get_exam(exam_code: str):
    """Case-insensitive lookup, returns None if the code doesn't exist."""
    if not exam_code:
        return None
    return EXAMS.get(exam_code.strip().upper())
