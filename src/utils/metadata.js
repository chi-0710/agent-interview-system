/**
 * 元数据比对工具
 *
 * 功能：判断某个文档段落是否匹配错题标签
 * 例如：errorTags 中有 { sections: ['Memory', 'Short-term'] }
 * 而当前段落 metadata 中有 { headers: ['Memory', 'Short-term'] }
 * 则判定为命中，应高亮
 */

/**
 * 检查段落是否命中错题标签
 * @param {{ headers?: string[]; line_start?: number }} metadata 段落 metadata
 * @param {{ tag: string; count: number; sections: string[] }[]} errorTags 错题标签数组
 * @returns {{ matched: boolean; tags: string[] }}
 */
export function matchErrorTags(metadata, errorTags) {
  if (!metadata || !errorTags || errorTags.length === 0) {
    return { matched: false, tags: [] };
  }

  const headers = metadata.headers || [];
  const matchedTags = [];

  for (const et of errorTags) {
    const sections = et.sections || [];
    // 如果 sections 是 headers 的子序列，即为命中
    const isMatch = sections.length > 0 && isSubsequence(sections, headers);
    if (isMatch) {
      matchedTags.push(et.tag);
    }
  }

  return {
    matched: matchedTags.length > 0,
    tags: matchedTags,
  };
}

/**
 * 判断 arrA 是否为 arrB 的子序列
 */
function isSubsequence(arrA, arrB) {
  const lowerB = arrB.map((h) => h.toLowerCase());
  const lowerA = arrA.map((h) => h.toLowerCase());
  let j = 0;
  for (let i = 0; i < lowerB.length && j < lowerA.length; i++) {
    if (lowerB[i] === lowerA[j]) {
      j++;
    }
  }
  return j === lowerA.length;
}

/**
 * 根据错题标签反向查找对应的文档段落标识
 * 返回需要高亮的 section 路径列表
 * @param {{ tag: string; count: number; sections: string[] }[]} errorTags
 * @returns {string[][]}
 */
export function getHighlightPaths(errorTags) {
  return errorTags
    .filter((et) => et.sections && et.sections.length > 0)
    .map((et) => et.sections);
}
