import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';
import ImageUploader from './ImageUploader';

const mockToast = jest.fn();

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

jest.mock('@/hooks/useToast', () => ({
  useToast: () => ({
    toast: mockToast,
  }),
}));

jest.mock('@/lib/file', () => ({
  uploadFile: jest.fn(),
}));

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    upfileByUrl: jest.fn(),
  },
}));

describe('ImageUploader', () => {
  beforeEach(() => {
    mockToast.mockReset();
    jest.mocked(api.upfileByUrl).mockReset();
  });

  test('does not emit an invalid resource when URL upload fails', async () => {
    const onChange = jest.fn();
    jest.mocked(api.upfileByUrl).mockRejectedValue(new Error('upload failed'));

    render(<ImageUploader onChange={onChange} />);

    fireEvent.change(
      screen.getByPlaceholderText(
        'component.fileUploader.pasteOrInputImageUrl',
      ),
      {
        target: { value: 'https://example.com/image.png' },
      },
    );
    fireEvent.click(screen.getByText('component.fileUploader.run'));

    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith({
        title: 'component.fileUploader.checkImageUrl',
        variant: 'destructive',
      });
    });

    expect(onChange).not.toHaveBeenCalledWith(
      expect.objectContaining({ resourceUrl: undefined }),
    );
    expect(
      screen.getByPlaceholderText(
        'component.fileUploader.pasteOrInputImageUrl',
      ),
    ).toBeInTheDocument();
  });
});
