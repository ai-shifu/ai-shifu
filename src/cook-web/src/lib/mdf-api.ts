/**
 * MDF Convert API Client
 * Calls third-party MDF conversion service
 */

import { getUserId, refreshUserIdExpiry } from './user';

/**
 * MDF conversion request parameters
 */
export interface MdfConvertRequest {
  text: string;
  language?: 'Chinese' | 'English';
  output_mode?: 'content' | 'both';
}

/**
 * MDF conversion response
 */
export interface MdfConvertResponse {
  content_prompt: string;
  request_id: string;
  timestamp: string;
  metadata: {
    input_length: number;
    output_length?: number;
    language: string;
    user_id: string;
  };
}

/**
 * API Error class
 */
export class ApiError extends Error {
  constructor(
    message: string,
    public code?: number,
    public response?: Response,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/**
 * Get common request headers
 */
function getCommonHeaders(): HeadersInit {
  const userId = getUserId();
  refreshUserIdExpiry();

  return {
    'Content-Type': 'application/json',
    'User-Id': userId,
  };
}

/**
 * Handle API response
 */
async function handleApiResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new ApiError(
      `API request failed: ${response.status} ${response.statusText}`,
      response.status,
      response,
    );
  }

  const data = await response.json();

  // Check for business error code
  if (data.code !== undefined && data.code !== 200 && data.code !== 0) {
    throw new ApiError(data.message || 'API returned error code', data.code);
  }

  return data;
}

/**
 * Convert document to Markdown Flow format
 *
 * @param request - Conversion request parameters
 * @returns Conversion result
 * @throws {ApiError} When API call fails
 *
 * @example
 * ```typescript
 * const result = await convertToMdf({
 *   text: 'Document content',
 *   language: 'Chinese',
 * })
 * console.log(result.content_prompt)
 * ```
 */
export async function convertToMdf(
  request: MdfConvertRequest,
): Promise<MdfConvertResponse> {
  try {
    // Get API base URL from environment variable
    const baseUrl =
      process.env.NEXT_PUBLIC_GEN_MDF_API_URL || 'http://localhost:8000';

    const response = await fetch(`${baseUrl}/gen/mdf-convert`, {
      method: 'POST',
      headers: getCommonHeaders(),
      body: JSON.stringify({
        text: request.text,
        language: request.language || 'Chinese',
        output_mode: request.output_mode || 'content',
        user_id: getUserId(),
      }),
    });

    return await handleApiResponse<MdfConvertResponse>(response);
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw new ApiError(
      `Network error: ${error instanceof Error ? error.message : 'Unknown error'}`,
    );
  }
}
