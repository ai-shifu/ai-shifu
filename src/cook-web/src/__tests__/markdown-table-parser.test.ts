/**
 * Tests for markdown table parsing utilities.
 */

import {
  parseMarkdownTableRow,
  parseMarkdownTableAlign,
  isMarkdownTableSeparatorLine,
  findFirstMarkdownTableBlock,
  markdownTableToSandboxHtml,
} from '@/c-utils/listen-mode/markdown-table-parser';

describe('parseMarkdownTableRow', () => {
  it('should parse a row with leading and trailing pipes', () => {
    expect(parseMarkdownTableRow('| Cell 1 | Cell 2 |')).toEqual([
      'Cell 1',
      'Cell 2',
    ]);
  });

  it('should parse a row without leading pipe', () => {
    expect(parseMarkdownTableRow('Cell 1 | Cell 2 |')).toEqual([
      'Cell 1',
      'Cell 2',
    ]);
  });

  it('should parse a row without trailing pipe', () => {
    expect(parseMarkdownTableRow('| Cell 1 | Cell 2')).toEqual([
      'Cell 1',
      'Cell 2',
    ]);
  });

  it('should trim whitespace from cells', () => {
    expect(parseMarkdownTableRow('|  Cell 1  |  Cell 2  |')).toEqual([
      'Cell 1',
      'Cell 2',
    ]);
  });

  it('should handle empty cells', () => {
    expect(parseMarkdownTableRow('| | Cell 2 |')).toEqual(['', 'Cell 2']);
  });
});

describe('parseMarkdownTableAlign', () => {
  it('should detect left alignment', () => {
    expect(parseMarkdownTableAlign('| :--- | :--- |')).toEqual([
      'left',
      'left',
    ]);
  });

  it('should detect center alignment', () => {
    expect(parseMarkdownTableAlign('| :---: | :---: |')).toEqual([
      'center',
      'center',
    ]);
  });

  it('should detect right alignment', () => {
    expect(parseMarkdownTableAlign('| ---: | ---: |')).toEqual([
      'right',
      'right',
    ]);
  });

  it('should detect no alignment (default)', () => {
    expect(parseMarkdownTableAlign('| --- | --- |')).toEqual(['', '']);
  });

  it('should detect mixed alignments', () => {
    expect(parseMarkdownTableAlign('| :--- | :---: | ---: | --- |')).toEqual([
      'left',
      'center',
      'right',
      '',
    ]);
  });

  it('should return empty string for invalid separator cells', () => {
    expect(parseMarkdownTableAlign('| :-- | --- |')).toEqual(['', '']);
  });

  it('should handle separators with varying dashes', () => {
    expect(parseMarkdownTableAlign('| :--- | :-----: | ---------: |')).toEqual([
      'left',
      'center',
      'right',
    ]);
  });
});

describe('isMarkdownTableSeparatorLine', () => {
  it('should return true for valid separator with 2 cells', () => {
    expect(isMarkdownTableSeparatorLine('| --- | --- |')).toBe(true);
  });

  it('should return true for valid separator with mixed alignments', () => {
    expect(isMarkdownTableSeparatorLine('| :--- | :---: | ---: |')).toBe(true);
  });

  it('should return false for separator with only 1 cell', () => {
    expect(isMarkdownTableSeparatorLine('| --- |')).toBe(false);
  });

  it('should return false for invalid separator pattern', () => {
    expect(isMarkdownTableSeparatorLine('| :-- | --- |')).toBe(false);
  });

  it('should return false for non-separator line', () => {
    expect(isMarkdownTableSeparatorLine('| Cell 1 | Cell 2 |')).toBe(false);
  });

  it('should handle separators with whitespace', () => {
    expect(isMarkdownTableSeparatorLine('|  :---  |  ---:  |')).toBe(true);
  });
});

describe('findFirstMarkdownTableBlock', () => {
  it('should find a simple 2-row table', () => {
    const text = '| A | B |\n| --- | --- |\n| 1 | 2 |';
    const result = findFirstMarkdownTableBlock(text);
    expect(result).toEqual({ start: 0, end: text.length });
  });

  it('should find a table with header and separator only', () => {
    const text = '| Header 1 | Header 2 |\n| :--- | ---: |';
    const result = findFirstMarkdownTableBlock(text);
    expect(result).toEqual({ start: 0, end: text.length });
  });

  it('should find a table in the middle of text', () => {
    const text =
      'Some text before\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\nSome text after';
    const result = findFirstMarkdownTableBlock(text);
    expect(result).not.toBeNull();
    expect(text.slice(result!.start, result!.end)).toBe(
      '| A | B |\n| --- | --- |\n| 1 | 2 |\n',
    );
  });

  it('should stop at blank line', () => {
    const text = '| A | B |\n| --- | --- |\n| 1 | 2 |\n\n| C | D |';
    const result = findFirstMarkdownTableBlock(text);
    expect(result).not.toBeNull();
    expect(text.slice(result!.start, result!.end)).toBe(
      '| A | B |\n| --- | --- |\n| 1 | 2 |\n',
    );
  });

  it('should stop at line without pipe', () => {
    const text = '| A | B |\n| --- | --- |\n| 1 | 2 |\nNot a table row';
    const result = findFirstMarkdownTableBlock(text);
    expect(result).not.toBeNull();
    expect(text.slice(result!.start, result!.end)).toBe(
      '| A | B |\n| --- | --- |\n| 1 | 2 |\n',
    );
  });

  it('should return null for empty string', () => {
    expect(findFirstMarkdownTableBlock('')).toBeNull();
  });

  it('should return null for text with no table', () => {
    expect(findFirstMarkdownTableBlock('Just some text')).toBeNull();
  });

  it('should return null for invalid table (no separator)', () => {
    const text = '| A | B |\n| 1 | 2 |';
    expect(findFirstMarkdownTableBlock(text)).toBeNull();
  });

  it('should return null for table with less than 2 cells', () => {
    const text = '| A |\n| --- |\n| 1 |';
    expect(findFirstMarkdownTableBlock(text)).toBeNull();
  });

  it('should handle table ending at end of string (no trailing newline)', () => {
    const text = '| A | B |\n| --- | --- |\n| 1 | 2 |';
    const result = findFirstMarkdownTableBlock(text);
    expect(result).toEqual({ start: 0, end: text.length });
  });
});

describe('markdownTableToSandboxHtml', () => {
  it('should convert a simple table to HTML', () => {
    const markdown = '| Name | Age |\n| --- | --- |\n| Alice | 25 |';
    const html = markdownTableToSandboxHtml(markdown);
    expect(html).toContain('<table>');
    expect(html).toContain('<thead>');
    expect(html).toContain('<tbody>');
    expect(html).toContain('<th>Name</th>');
    expect(html).toContain('<th>Age</th>');
    expect(html).toContain('<td>Alice</td>');
    expect(html).toContain('<td>25</td>');
  });

  it('should apply left alignment', () => {
    const markdown = '| Name |\n| :--- |\n| Alice |';
    const html = markdownTableToSandboxHtml(markdown);
    expect(html).toContain('style="text-align:left;"');
  });

  it('should apply center alignment', () => {
    const markdown = '| Name |\n| :---: |\n| Alice |';
    const html = markdownTableToSandboxHtml(markdown);
    expect(html).toContain('style="text-align:center;"');
  });

  it('should apply right alignment', () => {
    const markdown = '| Age |\n| ---: |\n| 25 |';
    const html = markdownTableToSandboxHtml(markdown);
    expect(html).toContain('style="text-align:right;"');
  });

  it('should apply mixed alignments', () => {
    const markdown =
      '| Left | Center | Right |\n| :--- | :---: | ---: |\n| A | B | C |';
    const html = markdownTableToSandboxHtml(markdown);
    expect(html).toContain('text-align:left;');
    expect(html).toContain('text-align:center;');
    expect(html).toContain('text-align:right;');
  });

  it('should escape HTML in cell contents', () => {
    const markdown = '| Code |\n| --- |\n| <script>alert("xss")</script> |';
    const html = markdownTableToSandboxHtml(markdown);
    expect(html).not.toContain('<script>');
    expect(html).toContain('&lt;script&gt;');
  });

  it('should wrap table in div', () => {
    const markdown = '| A | B |\n| --- | --- |';
    const html = markdownTableToSandboxHtml(markdown);
    expect(html).toMatch(/^<div><table>/);
    expect(html).toMatch(/<\/table><\/div>$/);
  });

  it('should return null for empty string', () => {
    expect(markdownTableToSandboxHtml('')).toBeNull();
  });

  it('should return null for single line', () => {
    expect(markdownTableToSandboxHtml('| A | B |')).toBeNull();
  });

  it('should return null for invalid table (no pipes)', () => {
    expect(markdownTableToSandboxHtml('Header\n---')).toBeNull();
  });

  it('should handle table with no body rows', () => {
    const markdown = '| Name | Age |\n| --- | --- |';
    const html = markdownTableToSandboxHtml(markdown);
    expect(html).toContain('<thead>');
    expect(html).toContain('<tbody></tbody>');
  });

  it('should handle multiple body rows', () => {
    const markdown =
      '| Name | Age |\n| --- | --- |\n| Alice | 25 |\n| Bob | 30 |\n| Charlie | 35 |';
    const html = markdownTableToSandboxHtml(markdown);
    expect(html).toContain('<td>Alice</td>');
    expect(html).toContain('<td>Bob</td>');
    expect(html).toContain('<td>Charlie</td>');
  });

  it('should filter out empty body rows', () => {
    const markdown = '| Name |\n| --- |\n\n| Alice |';
    const html = markdownTableToSandboxHtml(markdown);
    expect(html).toContain('<td>Alice</td>');
  });

  it('should handle cells with special characters', () => {
    const markdown = '| Char |\n| --- |\n| & < > " \' |';
    const html = markdownTableToSandboxHtml(markdown);
    expect(html).toContain('&amp;');
    expect(html).toContain('&lt;');
    expect(html).toContain('&gt;');
    expect(html).toContain('&quot;');
    expect(html).toContain('&#39;');
  });
});
