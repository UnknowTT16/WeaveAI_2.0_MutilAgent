// frontend/app/components/DataTable.js
'use client';

// 接收 onRowClick 和 selectedRowIdentifier props 以实现交互
export default function DataTable({ title, data, onRowClick, selectedRowIdentifier }) {
  if (!data || data.length === 0) {
    return <p className="text-gray-400">没有可显示的数据。</p>;
  }

  const headers = Object.keys(data[0]);
  
  // 确定用于比较行是否被选中的唯一键名
  const identifierKey = Object.keys(data[0]).includes('cluster') ? 'cluster' : headers[0];

  return (
    <div className="space-y-4">
      <h4 className="font-semibold text-white">{title}</h4>
      <div className="overflow-x-auto rounded-lg border border-gray-700">
        <table className="min-w-full divide-y divide-gray-700">
          <thead className="bg-gray-800">
            <tr>
              {headers.map((header) => (
                <th key={header} scope="col" className="py-3.5 px-4 text-left text-sm font-semibold text-white">
                  {/* 美化表头显示：替换下划线并移除特定文本 */}
                  {header.replace(/_/g, ' ').replace('is hot cluster', ' ')}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-700 bg-gray-900">
            {data.map((row, rowIndex) => {
              // 判断当前行是否被选中
              const isSelected = selectedRowIdentifier !== null && row[identifierKey] === selectedRowIdentifier;
              return (
                <tr 
                  key={rowIndex}
                  // 如果提供了 onRowClick 函数，则添加点击事件和对应的UI样式
                  onClick={() => onRowClick && onRowClick(row)}
                  className={`${onRowClick ? 'cursor-pointer hover:bg-gray-800 transition-colors duration-200' : ''} ${isSelected ? 'bg-indigo-900/50' : ''}`}
                >
                  {headers.map((header) => (
                    <td key={header} className="whitespace-nowrap px-4 py-4 text-sm text-gray-300">
                      {/* 优化不同数据类型的显示 */}
                      {typeof row[header] === 'boolean' ? (row[header] ? '🔥 热销' : '') : // 布尔值显示为图标
                       typeof row[header] === 'number' ? row[header].toFixed(2) : // 数字保留两位小数
                       row[header]}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}