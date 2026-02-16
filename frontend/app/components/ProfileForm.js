// frontend/app/components/ProfileForm.js
'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import { 
  Globe2, 
  ShoppingBag, 
  UserCircle2, 
  DollarSign, 
  Sparkles,
  ArrowRight
} from 'lucide-react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs) {
  return twMerge(clsx(inputs));
}

export default function ProfileForm({ onFormSubmit, isLoading }) {
  const [profileData, setProfileData] = useState({
    target_market: 'Germany',
    supply_chain: 'Consumer Electronics',
    seller_type: '品牌方',
    min_price: 30,
    max_price: 90,
  });

  const handleChange = (e) => {
    const { name, value } = e.target;
    setProfileData(prevData => ({ ...prevData, [name]: value }));
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    onFormSubmit({
      ...profileData,
      min_price: parseInt(profileData.min_price) || 0,
      max_price: parseInt(profileData.max_price) || 0,
    });
  };

  const inputClasses = "w-full bg-accent/50 border-border rounded-2xl p-4 text-foreground placeholder:text-muted-foreground focus:ring-2 focus:ring-gemini-blue/20 focus:border-gemini-blue outline-none transition-all";
  const labelClasses = "flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-muted-foreground mb-2 px-1";

  return (
    <div className="w-full max-w-xl mx-auto">
      <div className="text-center mb-8">
        <motion.div
          initial={{ scale: 0.5, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-gradient-to-tr from-gemini-blue to-gemini-purple text-white mb-4"
        >
          <Sparkles size={24} />
        </motion.div>
        <h3 className="text-2xl font-bold tracking-tight">配置战略分析方案</h3>
        <p className="text-muted-foreground mt-2">填写以下信息以启动多 Agent 深度调研</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Target Market */}
          <div>
            <label className={labelClasses}><Globe2 size={14} /> 目标市场</label>
            <input 
              type="text" 
              name="target_market" 
              placeholder="例如：Germany, Japan"
              value={profileData.target_market} 
              onChange={handleChange} 
              required 
              className={inputClasses}
            />
          </div>

          {/* Supply Chain */}
          <div>
            <label className={labelClasses}><ShoppingBag size={14} /> 核心品类</label>
            <input 
              type="text" 
              name="supply_chain" 
              placeholder="例如：Consumer Electronics"
              value={profileData.supply_chain} 
              onChange={handleChange} 
              required 
              className={inputClasses}
            />
          </div>
        </div>

        {/* Seller Type */}
        <div>
          <label className={labelClasses}><UserCircle2 size={14} /> 卖家身份</label>
          <select 
            name="seller_type" 
            value={profileData.seller_type} 
            onChange={handleChange} 
            className={cn(inputClasses, "appearance-none cursor-pointer")}
          >
            <option>品牌方</option>
            <option>工厂转型</option>
            <option>贸易商</option>
            <option>个人卖家</option>
          </select>
        </div>

        {/* Price Range */}
        <div className="bg-accent/30 p-6 rounded-[2rem] border border-border/50">
           <label className={labelClasses}><DollarSign size={14} /> 目标售价区间 (USD)</label>
           <div className="flex items-center gap-4">
              <div className="relative flex-grow">
                <span className="absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground">$</span>
                <input 
                  type="number" 
                  name="min_price" 
                  value={profileData.min_price} 
                  onChange={handleChange} 
                  required 
                  className={cn(inputClasses, "pl-8")}
                />
              </div>
              <div className="text-muted-foreground">至</div>
              <div className="relative flex-grow">
                <span className="absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground">$</span>
                <input 
                  type="number" 
                  name="max_price" 
                  value={profileData.max_price} 
                  onChange={handleChange} 
                  required 
                  className={cn(inputClasses, "pl-8")}
                />
              </div>
           </div>
        </div>

        <motion.button 
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          type="submit" 
          disabled={isLoading} 
          className="w-full flex items-center justify-center gap-3 py-5 px-4 rounded-2xl bg-foreground text-background font-bold text-lg transition-all disabled:opacity-50 shadow-xl shadow-foreground/5 hover:shadow-foreground/10"
        >
          {isLoading ? (
            <div className="flex items-center gap-2">
              <div className="w-5 h-5 border-2 border-background/30 border-t-background rounded-full animate-spin" />
              <span>正在初始化...</span>
            </div>
          ) : (
            <>
              <span>进入编排中心</span>
              <ArrowRight size={20} />
            </>
          )}
        </motion.button>
      </form>
    </div>
  );
}
