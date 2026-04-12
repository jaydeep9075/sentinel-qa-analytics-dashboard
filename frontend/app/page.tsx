"use client";
import Link from "next/link";

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-gray-800 to-black">
      {/* Hero Section */}
      <div className="relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-r from-blue-600/20 to-purple-600/20 blur-3xl" />
        <div className="relative container mx-auto px-6 py-24 text-center">
          <h1 className="text-5xl md:text-7xl font-bold bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent mb-6">
            Sentinel QA Intelligence
          </h1>
          <p className="text-xl text-gray-300 max-w-3xl mx-auto mb-8">
            AI-Powered Test Analytics for Modern QA Teams
          </p>
          <Link
            href="/login"
            className="inline-flex items-center gap-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-semibold px-8 py-4 rounded-xl transition-all shadow-lg shadow-blue-900/20"
          >
            Get Started →
          </Link>
        </div>
      </div>

      {/* Features */}
      <div className="container mx-auto px-6 py-16">
        <div className="grid md:grid-cols-3 gap-8">
          <div className="bg-white/5 backdrop-blur-lg rounded-2xl p-6 border border-white/10">
            <div className="text-4xl mb-4">💬</div>
            <h3 className="text-xl font-bold mb-2">Natural Language Chat</h3>
            <p className="text-gray-400">Ask questions in plain English – “Show me failed tests in checkout module”</p>
          </div>
          <div className="bg-white/5 backdrop-blur-lg rounded-2xl p-6 border border-white/10">
            <div className="text-4xl mb-4">📊</div>
            <h3 className="text-xl font-bold mb-2">Auto‑Generated Charts</h3>
            <p className="text-gray-400">Create visualisations instantly from natural language prompts</p>
          </div>
          <div className="bg-white/5 backdrop-blur-lg rounded-2xl p-6 border border-white/10">
            <div className="text-4xl mb-4">🎭</div>
            <h3 className="text-xl font-bold mb-2">Role‑Based Insights</h3>
            <p className="text-gray-400">CTO sees business risks, QA engineer sees technical details</p>
          </div>
        </div>

        <div className="mt-16 text-center">
          <h2 className="text-3xl font-bold mb-4">How It Works</h2>
          <div className="grid md:grid-cols-3 gap-8 mt-8">
            <div className="text-center">
              <div className="w-12 h-12 bg-blue-500/20 rounded-full flex items-center justify-center mx-auto mb-3 text-blue-400 font-bold">1</div>
              <p>Upload your test results (Allure, JUnit, CSV)</p>
            </div>
            <div className="text-center">
              <div className="w-12 h-12 bg-blue-500/20 rounded-full flex items-center justify-center mx-auto mb-3 text-blue-400 font-bold">2</div>
              <p>Ask questions or request charts in plain English</p>
            </div>
            <div className="text-center">
              <div className="w-12 h-12 bg-blue-500/20 rounded-full flex items-center justify-center mx-auto mb-3 text-blue-400 font-bold">3</div>
              <p>Get instant answers, visualisations, and release readiness reports</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
