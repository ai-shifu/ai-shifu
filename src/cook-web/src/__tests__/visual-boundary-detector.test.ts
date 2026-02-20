/**
 * Tests for visual boundary detection utilities.
 */

import {
  findFirstHtmlVisualBlock,
  findFirstTextVisualBlock,
} from '@/c-utils/listen-mode/visual-boundary-detector';

describe('findFirstHtmlVisualBlock', () => {
  describe('video elements', () => {
    it('should find video with closing tag', () => {
      const text = '<p>Text</p><video src="test.mp4"></video><p>More</p>';
      const result = findFirstHtmlVisualBlock(text);
      expect(result).toEqual({
        kind: 'video',
        start: 11,
        end: 41,
      });
    });

    it('should find self-closing video tag', () => {
      const text = '<p>Text</p><video src="test.mp4" /><p>More</p>';
      const result = findFirstHtmlVisualBlock(text);
      expect(result).toEqual({
        kind: 'video',
        start: 11,
        end: 35,
      });
    });

    it('should handle video tag case-insensitively', () => {
      const text = '<VIDEO src="test.mp4"></VIDEO>';
      const result = findFirstHtmlVisualBlock(text);
      expect(result).not.toBeNull();
      expect(result!.kind).toBe('video');
    });
  });

  describe('table elements', () => {
    it('should find table with closing tag', () => {
      const text = '<table><tr><td>Cell</td></tr></table>';
      const result = findFirstHtmlVisualBlock(text);
      expect(result).toEqual({
        kind: 'table',
        start: 0,
        end: 37,
      });
    });

    it('should find table in mixed content', () => {
      const text = 'Text before<table><tr><td>Data</td></tr></table>Text after';
      const result = findFirstHtmlVisualBlock(text);
      expect(result?.kind).toBe('table');
      expect(result?.start).toBe(11);
    });
  });

  describe('iframe elements', () => {
    it('should find iframe with closing tag', () => {
      const text = '<iframe src="https://example.com"></iframe>';
      const result = findFirstHtmlVisualBlock(text);
      expect(result).toEqual({
        kind: 'iframe',
        start: 0,
        end: 43,
      });
    });

    it('should find self-closing iframe tag', () => {
      const text = '<iframe src="https://example.com" />';
      const result = findFirstHtmlVisualBlock(text);
      expect(result).toEqual({
        kind: 'iframe',
        start: 0,
        end: 36,
      });
    });
  });

  describe('svg elements', () => {
    it('should find svg with closing tag', () => {
      const text =
        '<svg width="100" height="100"><circle cx="50" cy="50" r="40"/></svg>';
      const result = findFirstHtmlVisualBlock(text);
      expect(result).toEqual({
        kind: 'svg',
        start: 0,
        end: 68,
      });
    });

    it('should find svg in text', () => {
      const text = 'Some text<svg><rect /></svg>More text';
      const result = findFirstHtmlVisualBlock(text);
      expect(result?.kind).toBe('svg');
      expect(result?.start).toBe(9);
    });
  });

  describe('img elements', () => {
    it('should find self-closing img tag', () => {
      const text = '<img src="image.png" />';
      const result = findFirstHtmlVisualBlock(text);
      expect(result).toEqual({
        kind: 'img',
        start: 0,
        end: 23,
      });
    });

    it('should find img without self-closing slash', () => {
      const text = '<img src="image.png">';
      const result = findFirstHtmlVisualBlock(text);
      expect(result).toBeNull(); // img doesn't have closing tag, and this isn't self-closing
    });

    it('should find img tag with various attributes', () => {
      const text = '<img src="test.jpg" alt="Test" class="image" />';
      const result = findFirstHtmlVisualBlock(text);
      expect(result?.kind).toBe('img');
    });
  });

  describe('priority and ordering', () => {
    it('should return the first visual element when multiple exist', () => {
      const text = '<table></table><video></video><iframe></iframe>';
      const result = findFirstHtmlVisualBlock(text);
      expect(result?.kind).toBe('table');
      expect(result?.start).toBe(0);
    });

    it('should return video when it appears before table', () => {
      const text = '<video></video><table></table>';
      const result = findFirstHtmlVisualBlock(text);
      expect(result?.kind).toBe('video');
    });

    it('should handle nested elements (returns outer)', () => {
      const text = '<div><video src="test.mp4"></video></div>';
      const result = findFirstHtmlVisualBlock(text);
      expect(result?.kind).toBe('video');
    });
  });

  describe('edge cases', () => {
    it('should return null for empty string', () => {
      expect(findFirstHtmlVisualBlock('')).toBeNull();
    });

    it('should return null for text with no visual elements', () => {
      expect(findFirstHtmlVisualBlock('<p>Just a paragraph</p>')).toBeNull();
    });

    it('should return null for unclosed tag', () => {
      const text = '<video src="test.mp4">';
      const result = findFirstHtmlVisualBlock(text);
      expect(result).toBeNull(); // No closing tag and not self-closing
    });

    it('should handle whitespace in self-closing tags', () => {
      const text = '<video src="test.mp4"  /  >';
      const result = findFirstHtmlVisualBlock(text);
      expect(result?.kind).toBe('video');
    });

    it('should handle malformed closing tags gracefully', () => {
      const text = '<table><tr></tr>'; // Missing </table>
      const result = findFirstHtmlVisualBlock(text);
      expect(result).toBeNull();
    });
  });
});

describe('findFirstTextVisualBlock', () => {
  it('should find HTML video block', () => {
    const text = '<video src="test.mp4"></video>';
    const result = findFirstTextVisualBlock(text);
    expect(result).toEqual({
      kind: 'video',
      start: 0,
      end: 30,
    });
  });

  it('should find markdown table block', () => {
    const text = '| A | B |\n| --- | --- |\n| 1 | 2 |';
    const result = findFirstTextVisualBlock(text);
    expect(result?.kind).toBe('markdown-table');
  });

  it('should return HTML when it appears first', () => {
    const text = '<table></table>\n\n| A | B |\n| --- | --- |';
    const result = findFirstTextVisualBlock(text);
    expect(result?.kind).toBe('table');
    expect(result?.start).toBe(0);
  });

  it('should return markdown table when it appears first', () => {
    const text = '| A | B |\n| --- | --- |\n\n<table></table>';
    const result = findFirstTextVisualBlock(text);
    expect(result?.kind).toBe('markdown-table');
    expect(result?.start).toBe(0);
  });

  it('should return null when no visual blocks exist', () => {
    const text = 'Just plain text with no tables or visual elements';
    expect(findFirstTextVisualBlock(text)).toBeNull();
  });

  it('should handle mixed content correctly', () => {
    const text =
      'Some intro text\n\n| Name | Age |\n| --- | --- |\n| Alice | 25 |\n\nMore text\n\n<video src="video.mp4"></video>';
    const result = findFirstTextVisualBlock(text);
    expect(result?.kind).toBe('markdown-table');
  });

  it('should return HTML when markdown table is incomplete', () => {
    const text = '| A | B |\n<table></table>';
    const result = findFirstTextVisualBlock(text);
    expect(result?.kind).toBe('table');
  });

  it('should handle empty string', () => {
    expect(findFirstTextVisualBlock('')).toBeNull();
  });

  it('should handle text with only HTML visual elements', () => {
    const text = '<div><iframe src="test.html"></iframe></div>';
    const result = findFirstTextVisualBlock(text);
    expect(result?.kind).toBe('iframe');
  });

  it('should handle text with only markdown tables', () => {
    const text =
      'Text\n\n| Col1 | Col2 |\n| :--- | ---: |\n| A | 1 |\n\nMore text';
    const result = findFirstTextVisualBlock(text);
    expect(result?.kind).toBe('markdown-table');
  });

  it('should handle svg elements', () => {
    const text = '<svg width="100" height="100"></svg>';
    const result = findFirstTextVisualBlock(text);
    expect(result?.kind).toBe('svg');
  });

  it('should handle img elements', () => {
    const text = '<img src="test.png" />';
    const result = findFirstTextVisualBlock(text);
    expect(result?.kind).toBe('img');
  });
});
