# 操作系统内存管理

## 虚拟内存

虚拟内存是操作系统提供的一种抽象，它让每个进程都以为自己独占连续的地址空间。

### 核心概念

- **虚拟地址**：进程中使用的地址，由 CPU 中的 MMU（Memory Management Unit）翻译为物理地址。
- **物理地址**：内存硬件上的实际地址。
- **页面（Page）**：虚拟内存的基本单位，通常大小为 4KB。

```c
// 简单的地址转换示意
phys_addr = page_table[vpn] + offset;
```

## 分页机制

分页是现代操作系统内存管理的基础。页表存储了虚拟页到物理页的映射。

### 页表结构

| 层级 | 名称 | 用途 |
|------|------|------|
| Level 1 | PGD (Page Global Directory) | 顶级目录 |
| Level 2 | PMD (Page Middle Directory) | 中间目录 |
| Level 3 | PTE (Page Table Entry) | 页表项 |

```c
typedef struct {
    unsigned long pte_low;
    unsigned long pte_high;
} pte_t;
```

## TLB 与缓存

TLB（Translation Lookaside Buffer）是 MMU 内部的高速缓存，用于加速虚拟地址到物理地址的转换。

> **关键问题**：当进程切换时，TLB 如何处理？答案是 TLB flush —— 在 x86 架构上，写入 CR3 寄存器会自动刷掉所有 TLB 条目，除非使用了 PCID（Process-Context Identifier）。

### 短期记忆 vs 长期记忆

从认知科学角度看，TLB 就像计算机的"短期记忆"——容量小、速度快、易失。而物理内存则更像是"长期记忆"的载体。

## 页面置换算法

当物理内存不足时，操作系统必须决定将哪些页面换出到磁盘。

常见算法包括：
- **FIFO**：先进先出，简单但容易产生 Belady 异常
- **LRU**：最近最少使用，效果好但实现成本高
- **Clock 算法**：LRU 的近似实现，Linux 默认使用

```python
def clock_algorithm(pages, frames):
    """Clock 页面置换算法示意"""
    memory = [-1] * frames
    ref_bit = [0] * frames
    pointer = 0
    faults = 0
    
    for page in pages:
        if page in memory:
            ref_bit[memory.index(page)] = 1
            continue
        
        faults += 1
        while ref_bit[pointer] == 1:
            ref_bit[pointer] = 0
            pointer = (pointer + 1) % frames
        
        memory[pointer] = page
        ref_bit[pointer] = 1
        pointer = (pointer + 1) % frames
    
    return faults
```

## Belady 异常

Belady 异常是指：在某些页面置换算法（特别是 FIFO）中，增加物理页框数反而导致更多的缺页中断。这是一个反直觉的现象。LRU 算法不会出现 Belady 异常。
