"use client";
import Link from "next/link";
import { motion } from "framer-motion";

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-gray-900 to-black text-white selection:bg-blue-500/30">
      {/* Hero Section */}
      <div className="relative overflow-hidden pt-32 pb-20 lg:pt-48 lg:pb-32">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] bg-gradient-to-tr from-blue-600/20 to-purple-600/20 blur-[120px] rounded-full pointer-events-none" />
        
        <div className="relative container mx-auto px-6 text-center">
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8 }}
          >
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white/5 border border-white/10 text-sm font-medium text-blue-300 mb-8 backdrop-blur-sm">
              <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
              Meet Your AI Testing Assistant
            </div>
          </motion.div>

          <motion.h1 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.1 }}
            className="text-5xl md:text-7xl font-extrabold tracking-tight mb-8"
          >
            Understand Your Software Quality
            <br />
            <span className="bg-gradient-to-r from-blue-400 via-indigo-400 to-purple-400 bg-clip-text text-transparent">
              In Plain English
            </span>
          </motion.h1>

          <motion.p 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.2 }}
            className="text-lg md:text-xl text-gray-400 max-w-2xl mx-auto mb-10 leading-relaxed"
          >
            No technical jargon. Just ask questions about your product's readiness and get instant, clear answers and beautiful charts. Sentinel makes testing data accessible for everyone.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.3 }}
          >
            <Link
              href={typeof window !== 'undefined' && localStorage.getItem('token') ? "/dashboard" : "/login"}
              className="inline-flex items-center justify-center gap-3 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-semibold px-8 py-4 rounded-full transition-all shadow-[0_0_40px_-10px_rgba(59,130,246,0.5)] hover:shadow-[0_0_60px_-15px_rgba(59,130,246,0.7)] hover:-translate-y-1"
            >
              Start Exploring
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 7l5 5m0 0l-5 5m5-5H6" /></svg>
            </Link>
          </motion.div>
        </div>
      </div>

      {/* Features */}
      <div className="container mx-auto px-6 py-20 border-t border-white/5 bg-white/[0.02]">
        <div className="grid md:grid-cols-3 gap-8 max-w-5xl mx-auto">
          {features.map((feature, idx) => (
            <motion.div 
              key={idx}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: idx * 0.1 }}
              className="bg-white/[0.03] hover:bg-white/[0.05] backdrop-blur-xl rounded-2xl p-8 border border-white/5 transition-all group"
            >
              <div className="text-4xl mb-6 bg-white/[0.05] w-16 h-16 rounded-xl flex items-center justify-center group-hover:scale-110 transition-transform">
                {feature.icon}
              </div>
              <h3 className="text-xl font-semibold mb-3 text-white">{feature.title}</h3>
              <p className="text-gray-400 leading-relaxed">{feature.desc}</p>
            </motion.div>
          ))}
        </div>
      </div>
      {/* How it Works / Steps */}
      <div className="container mx-auto px-6 py-24 border-t border-white/5 relative">
        <div className="text-center mb-16">
          <h2 className="text-3xl md:text-5xl font-bold mb-4">How to Get Insights</h2>
          <p className="text-gray-400 max-w-2xl mx-auto">Three simple steps to transform your raw testing data into actionable intelligence.</p>
        </div>
        
        <div className="grid md:grid-cols-3 gap-12 max-w-5xl mx-auto relative">
          {/* Connecting line for desktop */}
          <div className="hidden md:block absolute top-12 left-[16%] right-[16%] h-0.5 bg-gradient-to-r from-blue-500/0 via-blue-500/20 to-blue-500/0" />

          {[
            {
              step: "1",
              title: "Upload Data",
              desc: "Import your test execution results from existing sources like Allure, JUnit XMLs, or CSVs.",
              color: "text-blue-400"
            },
            {
              step: "2",
              title: "Ask a Question",
              desc: "Type naturally. e.g., 'What is the most failed module?' or 'Give me top 10 slowest tests.'",
              color: "text-purple-400"
            },
            {
              step: "3",
              title: "Get Visual Answers",
              desc: "Instantly receive text summaries, generated charts, and clear readiness decisions.",
              color: "text-indigo-400"
            }
          ].map((item, idx) => (
            <motion.div 
              key={idx}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: idx * 0.2 }}
              className="relative text-center z-10"
            >
              <div className="w-24 h-24 mx-auto bg-[#0a0a0a] rounded-full border border-white/10 flex items-center justify-center text-4xl font-bold shadow-[0_0_30px_-5px_rgba(59,130,246,0.2)] mb-6">
                <span className={`bg-gradient-to-br from-white to-gray-500 bg-clip-text text-transparent ${item.color}`}>{item.step}</span>
              </div>
              <h3 className="text-2xl font-bold mb-3">{item.title}</h3>
              <p className="text-gray-400 leading-relaxed px-4">{item.desc}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  );
}

const features = [
  {
    icon: "💬",
    title: "Talk to your data",
    desc: "Just ask 'How many tests failed today?' or 'Is the payment feature stable?' and get clear, instant answers."
  },
  {
    icon: "📊",
    title: "Instant visual reports",
    desc: "Need an update for an executive meeting? Sentinel generates beautiful charts on the fly with a simple request."
  },
  {
    icon: "🎯",
    title: "Tailored to your role",
    desc: "Whether you're a manager tracking project health or an engineer debugging code, Sentinel speaks your language."
  }
];
