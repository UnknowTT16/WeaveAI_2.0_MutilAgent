'use client';

import { useMemo, useState } from 'react';

export const DEFAULT_PROFILE_DRAFT = {
  target_market: '德国',
  supply_chain: '消费电子',
  seller_type: '品牌方',
  min_price: 30,
  max_price: 90,
};

export function normalizeProfileDraft(raw = {}) {
  const next = {
    ...DEFAULT_PROFILE_DRAFT,
    ...(raw && typeof raw === 'object' ? raw : {}),
  };
  next.min_price = Number.parseInt(String(next.min_price), 10) || 0;
  next.max_price = Number.parseInt(String(next.max_price), 10) || 0;
  return next;
}

export default function ProfileForm({
  value,
  onChange,
  onFormSubmit,
  isLoading,
  submitLabel = '开始分析',
  showTitle = true,
}) {
  const controlled = Boolean(value) && typeof onChange === 'function';
  const [internalValue, setInternalValue] = useState(DEFAULT_PROFILE_DRAFT);

  const profileData = useMemo(
    () => normalizeProfileDraft(controlled ? value : internalValue),
    [controlled, value, internalValue]
  );

  const updateValue = (next) => {
    if (controlled) {
      onChange(next);
      return;
    }
    setInternalValue(next);
  };

  const handleChange = (event) => {
    const { name, value: fieldValue } = event.target;
    updateValue({
      ...profileData,
      [name]: name.includes('price') ? Number.parseInt(fieldValue || '0', 10) : fieldValue,
    });
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    if (typeof onFormSubmit !== 'function') return;
    onFormSubmit(normalizeProfileDraft(profileData));
  };

  return (
    <div className="w-full rounded-3xl border border-border bg-card/90 p-5 shadow-sm md:p-7">
      {showTitle && (
        <div className="mb-5">
          <h2 className="section-title">告诉我们你的目标，我们帮你开始分析</h2>
          <p className="mt-2 text-sm text-muted-foreground">填写这 5 项信息即可开始。后续你可以在偏好页调整高级参数。</p>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div className="space-y-1.5">
            <label htmlFor="target_market" className="text-xs font-medium text-muted-foreground">目标市场</label>
            <input
              id="target_market"
              name="target_market"
              type="text"
              autoComplete="off"
              spellCheck={false}
              placeholder="例如：德国、美国、日本…"
              value={profileData.target_market}
              onChange={handleChange}
              required
              className="w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm"
            />
          </div>

          <div className="space-y-1.5">
            <label htmlFor="supply_chain" className="text-xs font-medium text-muted-foreground">核心品类</label>
            <input
              id="supply_chain"
              name="supply_chain"
              type="text"
              autoComplete="off"
              spellCheck={false}
              placeholder="例如：消费电子、家居收纳…"
              value={profileData.supply_chain}
              onChange={handleChange}
              required
              className="w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm"
            />
          </div>
        </div>

        <div className="space-y-1.5">
          <label htmlFor="seller_type" className="text-xs font-medium text-muted-foreground">卖家类型</label>
          <select
            id="seller_type"
            name="seller_type"
            value={profileData.seller_type}
            onChange={handleChange}
            className="w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm"
          >
            <option value="品牌方">品牌方</option>
            <option value="工厂转型">工厂转型</option>
            <option value="贸易商">贸易商</option>
            <option value="个人卖家">个人卖家</option>
          </select>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div className="space-y-1.5">
            <label htmlFor="min_price" className="text-xs font-medium text-muted-foreground">最低售价（USD）</label>
            <input
              id="min_price"
              name="min_price"
              type="number"
              min="0"
              inputMode="numeric"
              autoComplete="off"
              value={profileData.min_price}
              onChange={handleChange}
              required
              className="w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm numeric"
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="max_price" className="text-xs font-medium text-muted-foreground">最高售价（USD）</label>
            <input
              id="max_price"
              name="max_price"
              type="number"
              min="0"
              inputMode="numeric"
              autoComplete="off"
              value={profileData.max_price}
              onChange={handleChange}
              required
              className="w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm numeric"
            />
          </div>
        </div>

        <button
          type="submit"
          disabled={isLoading}
          className="inline-flex h-11 items-center justify-center rounded-xl bg-foreground px-5 text-sm font-semibold text-background transition-transform duration-200 hover:scale-[1.01] active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isLoading ? '分析启动中…' : submitLabel}
        </button>
      </form>
    </div>
  );
}
