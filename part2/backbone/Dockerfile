FROM golang:1.24 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /out/api ./cmd/api && CGO_ENABLED=0 go build -o /out/worker ./cmd/worker && CGO_ENABLED=0 go build -o /out/check ./cmd/check && CGO_ENABLED=0 go build -o /out/bench ./cmd/bench

FROM alpine:3.20
COPY --from=build /out/api /usr/local/bin/api
COPY --from=build /out/worker /usr/local/bin/worker
COPY --from=build /out/check /usr/local/bin/check
COPY --from=build /out/bench /usr/local/bin/bench
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/api"]
