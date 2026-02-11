import streamlit as st
import pandas as pd

from langchain_core.output_parsers import JsonOutputParser
from openai import OpenAI

# Initialize LLM client
client = st.session_state.openai_client


# ---------- FEEDBACK AGENT ----------
class FeedbackAgent:
    def __init__(self, conversation_results: list, llm):
        self.results = conversation_results
        self.llm = llm
        self.metrics = {}
        self.score = 0
        self.feedback_text = {}

    # ---------- LOGIC ANALYSIS ----------
    def analyze_triggers(self):
        trigger_count = sum(len(r.get("detected_triggers", [])) for r in self.results)
        trigger_repetition = trigger_count / max(1, len(self.results))
        return trigger_count, trigger_repetition

    def analyze_trust_trends(self):
        trust_scores = [r.get("trust_score", 0) for r in self.results]
        increases = sum(1 for i in range(1, len(trust_scores)) if trust_scores[i] > trust_scores[i-1])
        decreases = sum(1 for i in range(1, len(trust_scores)) if trust_scores[i] < trust_scores[i-1])
        return increases, decreases

    def analyze_info_ratio(self):
        total_msgs = len(self.results)
        total_info = sum(len(r.get("info_to_reveal", [])) for r in self.results)
        ratio = total_info / max(1, total_msgs)
        return total_info, ratio

    def analyze_mistakes(self):
        mistakes = [log for r in self.results for log in r.get("analysis_log", []) if "BREACH" in log]
        return len(mistakes)

    def analyze_phases(self):
        trust_scores = [r.get("trust_score", 0) for r in self.results]
        if not trust_scores:
            return "neutral"
        return "increment" if trust_scores[-1] > trust_scores[0] else "decrement"

    def compute_metrics(self):
        triggers, repetition = self.analyze_triggers()
        inc, dec = self.analyze_trust_trends()
        total_info, ratio = self.analyze_info_ratio()
        mistakes = self.analyze_mistakes()
        phases = self.analyze_phases()

        self.metrics = {
            "trigger_count": triggers,
            "trigger_repetition": repetition,
            "trust_increases": inc,
            "trust_decreases": dec,
            "info_revealed": total_info,
            "info_ratio": ratio,
            "mistakes": mistakes,
            "phase_trend": phases
        }

    def calculate_score(self):
        score = 10
        score -= self.metrics["mistakes"] * 1.5
        score -= self.metrics["info_ratio"] * 2
        score += min(self.metrics["trigger_count"], 5) * 0.5
        score += self.metrics["trust_increases"] * 0.2
        score = max(0, min(10, round(score, 1)))
        self.score = score

    # ---------- AI FEEDBACK ----------
    def generate_ai_feedback(self):
        prompt = f"""
        You are a **phishing training coach**. 
        The trainee is acting as the attacker, and the AI agent is the victim. 

        Your job is to evaluate how good the trainee was at performing a social engineering (vishing) attack.

        Focus heavily on:
        - How well they applied **time pressure** (urgency, deadlines, fear of missing out).
        - How well they used **trigger words** and psychological manipulation.
        - The **quality of user inputs** (were they convincing? manipulative? sloppy?).
        - If trust scores increased or decreased, explain *why* that happened.
        - If information was revealed, explain how it was obtained.
        - If mistakes happened, explain what they were and why they weakened the attack.

        Metrics summary:
        {self.metrics}

        Conversation (user = attacker, agent = victim):
        {self.results}

        Provide JSON with:
        {{
            "strengths": ["..."],
            "weaknesses": ["..."],
            "turn_analysis": {{
                "Turn 1": "Feedback on user input + agent response",
                "Turn 2": "Feedback ...",
                ...
            }},
            "suggestions": ["...", "...", "..."]
        }}
        """
        parser = JsonOutputParser()
        response = self.llm.chat.completions.create(
            model =client,
            messages=[{"role": "user", "content": prompt}]
        )
        parsed = parser.parse(response.choices[0].message.content)
        self.feedback_text = parsed

    # ---------- RUN PIPELINE ----------
    def run(self):
        self.compute_metrics()
        self.calculate_score()
        self.generate_ai_feedback()
        return {
            "score": self.score,
            "metrics": self.metrics,
            "feedback": self.feedback_text
        }

# -------------VOICE FEEDBACK -------------------------------------------
TRUST_THRESHOLDS = {
    "no_info": (0, 3.9999),
    "basic_info": (4, 6.9999),
    "sensitive_info": (7, 8.9999),
    "critical_info": (9, 10.0000)
}

INFO_CATEGORIES = {
    "basic": ["name", "location", "job"],
    "sensitive": ["phone", "email", "address"], 
    "critical": ["password", "ssn", "account", "credit_card"]
}

class FeedbackAgent(FeedbackAgent):
    def generate_ai_voice_feedback(self):
        feedback_data = {
            "score": self.score,
            "metrics": self.metrics,
            "results": self.results,
            "trust_thresholds": TRUST_THRESHOLDS,
            "info_categories": INFO_CATEGORIES
        }

        prompt = f"""
            You are a phishing training coach speaking directly to a trainee. 
            Provide a conversational, informal voice-style feedback about their vishing attempt.

            Example of how to speak (short, informal, 3 sentences): 
            'uyour total score is 6.5 out of ten and i'll tell u why exactly u lost a few points and what good things u did. 
            When u asked me for a password but ur trust score wasn't high enough yet, that was a mistake—be careful to gain my trust first before asking for info! 
            Also, ur use of time pressure was good but u didn't use it consistently, but u did well on being polite and building context.'

            Now, using the following data:

            - Total Score: {feedback_data['score']}
            - Metrics: {feedback_data['metrics']}
            - Conversation Results: {feedback_data['results']}
            - Trust Thresholds: {feedback_data['trust_thresholds']}
            - Info Categories: {feedback_data['info_categories']}

            Provide a feedback in the same style as the example above, highlighting mistakes, good actions, and advice for improvement.
            Output as a single coherent text suitable for reading aloud.
            """

        response = self.llm.chat.completions.create(
            model=client,
            messages=[{"role": "user", "content": prompt}]
        )

        self.voice_feedback = response.choices[0].message.content
        return self.voice_feedback


# ---------- STREAMLIT UI ----------
st.title("📊 Feedback & Results")
st.sidebar.success("Select a page from the sidebar")



def text_to_speech(text):
    try:
        response = client.audio.speech.create(
            model="tts-1",
            voice="alloy",
            input=text
        )
        return response.content
    except Exception as e:
        st.error(f"Error generating speech: {str(e)}")
        return None


if "results" not in st.session_state or not st.session_state.results:
    st.info("⚠️ No results collected yet. Go back to the conversation page and try again.")
else:
    results = st.session_state.results

    # Run FeedbackAgent
    agent = FeedbackAgent(results, st.session_state.llm)
    feedback_output = agent.run()

    score = feedback_output["score"]
    metrics = feedback_output["metrics"]
    feedback = feedback_output["feedback"]

    dashboard, analytics, suggestions = st.tabs(["📊 Dashboard", "📈 Analytics", "💡 Suggestions"])

    # ---------- DASHBOARD ----------
    with dashboard:
        st.header("Dashboard")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(label="Performance Score", value=f"{score}/10")
        with col2:
            st.metric(label="Triggers Used", value=metrics["trigger_count"])
        with col3:
            st.metric(label="Information Obtained", value=metrics["info_revealed"])

        trust_scores = [r.get("trust_score", 0) for r in results]
        if trust_scores:
            df_scores = pd.DataFrame({"Turn": range(1, len(trust_scores)+1), "Trust Score": trust_scores})
            df_scores.set_index("Turn", inplace=True)
            st.line_chart(df_scores[["Trust Score"]])

    # ---------- ANALYTICS ----------
    with analytics:
        st.header("Analytics")
        if feedback and "turn_analysis" in feedback:
            for turn, analysis in feedback["turn_analysis"].items():
                st.subheader(turn)
                st.write(analysis)

        st.subheader("General Observations")
        st.write(f"- Mistakes: {metrics['mistakes']}")
        st.write(f"- Trust trend: {metrics['phase_trend']}")
        st.write(f"- Info/Msg Ratio: {metrics['info_ratio']:.2f}")

    # ---------- SUGGESTIONS ----------
    with suggestions:
        st.header("Suggestions")
        if feedback:
            st.subheader("✅ Strengths")
            for s in feedback.get("strengths", []):
                st.write(f"- {s}")

            st.subheader("⚠️ Weaknesses")
            for w in feedback.get("weaknesses", []):
                st.write(f"- {w}")

            st.subheader("💡 Suggestions")
            for sug in feedback.get("suggestions", []):
                st.write(f"- {sug}")

    # ✅ FIX APPLIED HERE — voice feedback now inside else block
    voice_feedback_text = agent.generate_ai_voice_feedback()

    with st.expander("🎙️ Voice-Style Feedback"):
        st.text_area("Feedback", value=voice_feedback_text, height=400)

        if st.button("🔊 Play Feedback"):
            audio_bytes = text_to_speech(voice_feedback_text)
            if audio_bytes:
                st.audio(audio_bytes, format="audio/mp3")
