// Package cold is the object-store client for the cold tier. It stores opaque bytes by name;
// encryption and object layout decisions belong to the callers.
package cold

import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"sort"
	"time"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
)

// ErrNotFound is returned by Get for a missing object.
var ErrNotFound = errors.New("cold: object not found")

// Config locates the MinIO server and bucket. The endpoint is host:port and the connection is plain HTTP.
type Config struct {
	Endpoint  string
	AccessKey string
	SecretKey string
	Bucket    string
}

// Client reads and writes objects in one bucket.
type Client struct {
	mc     *minio.Client
	bucket string
}

// Open connects and creates the bucket if it is missing. Two nodes creating the same bucket at once both succeed.
func Open(ctx context.Context, cfg Config) (*Client, error) {
	mc, err := minio.New(cfg.Endpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(cfg.AccessKey, cfg.SecretKey, ""),
		Secure: false,
	})
	if err != nil {
		return nil, fmt.Errorf("cold: connect: %w", err)
	}
	exists, err := mc.BucketExists(ctx, cfg.Bucket)
	if err != nil {
		return nil, fmt.Errorf("cold: check bucket %q: %w", cfg.Bucket, err)
	}
	if !exists {
		if err := mc.MakeBucket(ctx, cfg.Bucket, minio.MakeBucketOptions{}); err != nil {
			// A concurrent Open may have created it between the check and now.
			code := minio.ToErrorResponse(err).Code
			if code != "BucketAlreadyOwnedByYou" && code != "BucketAlreadyExists" {
				return nil, fmt.Errorf("cold: create bucket %q: %w", cfg.Bucket, err)
			}
		}
	}
	return &Client{mc: mc, bucket: cfg.Bucket}, nil
}

// Put stores data under name, replacing any existing object of that name.
func (c *Client) Put(ctx context.Context, name string, data []byte) error {
	_, err := c.mc.PutObject(ctx, c.bucket, name, bytes.NewReader(data), int64(len(data)), minio.PutObjectOptions{})
	if err != nil {
		return fmt.Errorf("cold: put: %w", err)
	}
	return nil
}

// Get returns the object's bytes, or ErrNotFound.
func (c *Client) Get(ctx context.Context, name string) ([]byte, error) {
	obj, err := c.mc.GetObject(ctx, c.bucket, name, minio.GetObjectOptions{})
	if err != nil {
		return nil, fmt.Errorf("cold: get: %w", err)
	}
	defer obj.Close()
	data, err := io.ReadAll(obj)
	if err != nil {
		if minio.ToErrorResponse(err).Code == "NoSuchKey" {
			return nil, ErrNotFound
		}
		return nil, fmt.Errorf("cold: get: %w", err)
	}
	return data, nil
}

// ObjectName returns a fresh, never reused object name. kind "bucket" names a day bucket
// (day is the UTC day number since the epoch); kind "snapshot" names a snapshot and ignores day.
func ObjectName(tenantID, kind string, day int64) string {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		panic("cold: crypto/rand failed: " + err.Error())
	}
	id := hex.EncodeToString(b[:])
	if kind == "snapshot" {
		return tenantID + "/snapshot/" + id + ".json.enc"
	}
	return tenantID + "/buckets/" + time.Unix(day*86400, 0).UTC().Format("2006-01-02") + "/" + id + ".jsonl.enc"
}

// List returns every object name under prefix, recursively and sorted.
func (c *Client) List(ctx context.Context, prefix string) ([]string, error) {
	var names []string
	for o := range c.mc.ListObjects(ctx, c.bucket, minio.ListObjectsOptions{Prefix: prefix, Recursive: true}) {
		if o.Err != nil {
			return nil, fmt.Errorf("cold: list: %w", o.Err)
		}
		names = append(names, o.Key)
	}
	sort.Strings(names)
	return names, nil
}

// Delete removes the object. A missing object is already deleted and returns nil.
func (c *Client) Delete(ctx context.Context, name string) error {
	if err := c.mc.RemoveObject(ctx, c.bucket, name, minio.RemoveObjectOptions{}); err != nil {
		if minio.ToErrorResponse(err).Code == "NoSuchKey" {
			return nil
		}
		return fmt.Errorf("cold: delete: %w", err)
	}
	return nil
}
