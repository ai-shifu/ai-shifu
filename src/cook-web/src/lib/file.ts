/**
 * File upload utility functions
 */
import { getToken } from "@/local/local";
import { v4 as uuidv4 } from 'uuid';

/**
 * Upload a file to the server using FormData and fetch
 * @param file - The file to upload
 * @param url - The API endpoint URL
 * @param params - Additional parameters to include in the request
 * @param headers - Additional headers to include in the request
 * @param onProgress - Optional callback for upload progress
 * @returns Promise with the server response
 */
export const uploadFile = async (
  file: File,
  url: string,
  params?: Record<string, string>,
  headers?: Record<string, string>,
  onProgress?: (progress: number) => void
): Promise<Response> => {
  // Create a new FormData instance
  const formData = new FormData();

  // Append the file to the FormData
  formData.append('file', file);

  // Append any additional parameters
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      formData.append(key, value);
    });
  }

  // If we have a progress callback and the browser supports XMLHttpRequest
  if (onProgress && typeof XMLHttpRequest !== 'undefined') {
    return new Promise(async (resolve, reject) => {
      const xhr = new XMLHttpRequest();

      xhr.open('POST', url);

      // Get token
      const token = await getToken();

      // Add headers if provided
      if (headers) {
        Object.entries(headers).forEach(([key, value]) => {
          xhr.setRequestHeader(key, value);
        });
      }

      // Add token headers
      if (token) {
        xhr.setRequestHeader("Authorization", `Bearer ${token}`);
        xhr.setRequestHeader("Token", token);
        xhr.setRequestHeader("X-Request-ID", uuidv4().replace(/-/g, ''));
      }

      xhr.upload.addEventListener('progress', (event) => {
        if (event.lengthComputable) {
          const progress = Math.round((event.loaded / event.total) * 100);
          onProgress(progress);
        }
      });

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          const response = new Response(xhr.response, {
            status: xhr.status,
            statusText: xhr.statusText,
            headers: new Headers(
              xhr.getAllResponseHeaders()
                .split('\r\n')
                .filter(Boolean)
                .reduce((acc, header) => {
                  const [key, value] = header.split(': ');
                  acc[key.toLowerCase()] = value;
                  return acc;
                }, {} as Record<string, string>)
            )
          });
          resolve(response);
        } else {
          reject(new Error(`HTTP Error: ${xhr.status}`));
        }
      };

      xhr.onerror = () => {
        reject(new Error('Network Error'));
      };

      xhr.send(formData);
    });
  } else {
    // Use standard fetch API if no progress tracking is needed
    // Get token
    const token = await getToken();

    // Prepare headers
    let mergedHeaders = headers ? { ...headers } : {};

    // Add token headers
    if (token) {
      mergedHeaders = {
        ...mergedHeaders,
        "Authorization": `Bearer ${token}`,
        "Token": token,
        "X-API-MODE": "admin",
        "X-Request-ID": uuidv4().replace(/-/g, '')
      };
    }

    const requestOptions: RequestInit = {
      method: 'POST',
      body: formData,
      headers: mergedHeaders,
    };

    return fetch(url, requestOptions);
  }
};

/**
 * Upload multiple files to the server
 * @param files - Array of files to upload
 * @param url - The API endpoint URL
 * @param fieldName - The field name to use for each file (default: 'files')
 * @param params - Additional parameters to include in the request
 * @param headers - Additional headers to include in the request
 * @returns Promise with the server response
 */
export const uploadMultipleFiles = async (
  files: File[],
  url: string,
  fieldName: string = 'files',
  params?: Record<string, string>,
  headers?: Record<string, string>
): Promise<Response> => {
  const formData = new FormData();

  // Append each file to the FormData with the same field name
  files.forEach((file, index) => {
    formData.append(`${fieldName}[${index}]`, file);
  });

  // Append any additional parameters
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      formData.append(key, value);
    });
  }

  // Get token
  const token = await getToken();

  // Prepare headers
  let mergedHeaders = headers ? { ...headers } : {};

  // Add token headers
  if (token) {
    mergedHeaders = {
      ...mergedHeaders,
      "Authorization": `Bearer ${token}`,
      "Token": token,
      "X-API-MODE": "admin",
      "X-Request-ID": uuidv4().replace(/-/g, '')
    };
  }

  const requestOptions: RequestInit = {
    method: 'POST',
    body: formData,
    headers: mergedHeaders,
  };

  return fetch(url, requestOptions);
};

/**
 * Upload a file with a custom name
 * @param file - The file to upload
 * @param customName - Custom name for the file
 * @param url - The API endpoint URL
 * @param params - Additional parameters to include in the request
 * @param headers - Additional headers to include in the request
 * @returns Promise with the server response
 */
export const uploadFileWithCustomName = async (
  file: File,
  customName: string,
  url: string,
  params?: Record<string, string>,
  headers?: Record<string, string>
): Promise<Response> => {
  // Create a new File object with the custom name
  const renamedFile = new File([file], customName, { type: file.type });

  return uploadFile(renamedFile, url, params, headers);
};
