---
name: leetcode-layout
description: LeetCode/每日1题 文件夹结构和文件命名规范
metadata:
  type: project
---

# LeetCode 每日1题 目录布局与命名规范

根目录：`LeetCode/每日1题/`

## 日期文件夹命名
格式：`DDMM`（日+月，两位两位）
示例：`2609` → 9月26日

## 题目描述文件
路径：`LeetCode/每日1题/<DDMM>/序号_LeetCode题号_题目名.txt`
示例：`LeetCode/每日1题/2609/17_1477_找两个和为目标值且不重叠的子数组.txt`

其中 `序号` 是每日题目的序号（如17）。

## Java 解法
路径：`LeetCode/每日1题/Java/<DDMM>/J序号.java`
示例：`LeetCode/每日1题/Java/2609/J17.java`
文件名前缀为 `J`。

## Python 解法
路径：`LeetCode/每日1题/Python/<DDMM>/序号.py`
示例：`LeetCode/每日1题/Python/2609/17.py`
文件名无前缀，直接用序号。

## 注意
- `.class` 文件是编译产物，已被 git 删除（应加入 .gitignore）。
- 日期文件夹 `DDMM` 在题目描述目录和语言目录下各有一份，保持同步。
